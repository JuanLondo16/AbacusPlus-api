import logging
import re
import unicodedata
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.tax import Tax

logger = logging.getLogger(__name__)


def _normalizar(valor: str) -> str:
    """Nombre comparable: sin tildes, sin mayúsculas, sin puntuación de cola.

    El catálogo real trae parejas como «ReteIVA 15%» y «ReteIVA 15%.», o «autorretencion» y
    «autorretención.», que son el mismo impuesto importado dos veces con distinta higiene.
    Emparejar literalmente dejaría fuera justo a las filas heredadas que hay que corregir.
    """
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", valor or "") if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().strip(".").strip().lower()


class TaxRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(self, taxes: Iterable[dict], replace: bool = False) -> int:
        """Sincroniza el catálogo **conservando el id de SIIGO como clave**.

        La identidad de un impuesto es su id en SIIGO, no su nombre: es el dato que viaja de
        vuelta en `retentions` y en `items[].taxes` al contabilizar. Una fila nacida de la
        secuencia local lleva una clave que solo existe aquí, y SIIGO la rechaza con
        `The id doesn't exist`.

        Las filas heredadas no se pueden dejar como están ni borrar sin más: hay documentos
        apuntando a ellas. Se **reidentifican**: adoptan el id de SIIGO y se reapuntan todas
        las referencias que las citan, en la misma transacción.

        El emparejamiento va en DOS fases, y el orden importa. El catálogo real tiene cinco
        impuestos al 19% —«IVA 19%», «IVA 19%.», «Iva servicios 19%», «Iva servicios 19%.»,
        «Iva Exterior 19%»—. En una sola pasada, un impuesto de SIIGO podía reclamar por
        porcentaje la fila que le correspondía por nombre a otro; el que llegaba después
        chocaba contra el `UNIQUE(name)` y tumbaba la sincronización entera. Emparejar por
        nombre a todos primero elimina esa competencia: el porcentaje solo decide entre las
        filas que ningún nombre reclamó.

        `replace=True` (modo `replace` del import por Excel) borra TODO el catálogo antes de
        reconstruirlo con el archivo. El borrado usa `flush()`, no `commit()`: sigue siendo
        parte de esta misma transacción, así que si cualquier fila posterior falla, el único
        `commit()` del método (al final) nunca se alcanza y el borrado se deshace con el resto
        —el llamador (`get_tenant_db`) cierra la sesión sin confirmar, lo que revierte la
        transacción pendiente—. El catálogo nunca queda vacío por un archivo que fallaba a
        mitad de la importación. ADVERTENCIA: a diferencia de `replace` en centros de costo o
        productos, aquí el borrado alcanza también los impuestos sincronizados desde SIIGO; una
        factura que ya referencie un impuesto eliminado por el `replace` queda con una
        referencia inválida si el impuesto no vuelve a aparecer en el archivo.
        """
        items = list(taxes)
        if replace:
            self.db.query(Tax).delete(synchronize_session=False)
            self.db.flush()
        ids_de_siigo = {int(item["id"]) for item in items if item.get("id") is not None}
        reclamadas: set[int] = set()

        # ── Fase 1: nombre EXACTO ─────────────────────────────────────────────
        # Va antes que el nombre normalizado y no al revés. Los dos catálogos tienen los
        # mismos nombres, incluidas parejas como «IVA 19%» y «IVA 19%.», que normalizan
        # igual. Emparejando primero por lo normalizado, «IVA 19%» podía llevarse la fila de
        # «IVA 19%.» y dejar la suya libre: el cruce no pierde datos, pero al escribir el
        # nombre definitivo choca con la fila que aún no se ha procesado. Por el nombre
        # exacto cada impuesto encuentra el suyo y no hay cruce.
        asignaciones: dict[int, int] = {}
        candidatos = []
        for item in items:
            siigo_id = item.get("id")
            if siigo_id is None:
                continue
            siigo_id = int(siigo_id)
            if self.db.query(Tax).filter(Tax.id == siigo_id).one_or_none() is not None:
                continue
            candidatos.append((siigo_id, item))

        pendientes = []
        for siigo_id, item in candidatos:
            heredada = self._buscar_por_nombre_exacto(item, ids_de_siigo, reclamadas)
            if heredada is not None:
                reclamadas.add(heredada)
                asignaciones[siigo_id] = heredada
            else:
                pendientes.append((siigo_id, item))

        # ── Fase 2: nombre normalizado, para el que se escribió distinto ──────
        restantes = []
        for siigo_id, item in pendientes:
            heredada = self._buscar_por_nombre(item, ids_de_siigo, reclamadas)
            if heredada is not None:
                reclamadas.add(heredada)
                asignaciones[siigo_id] = heredada
            else:
                restantes.append((siigo_id, item))

        # ── Fase 3: lo que ningún nombre reclamó, por (tipo, porcentaje) ──────
        for siigo_id, item in restantes:
            heredada = self._buscar_por_tipo_y_porcentaje(item, ids_de_siigo, reclamadas)
            if heredada is not None:
                reclamadas.add(heredada)
                asignaciones[siigo_id] = heredada

        # ── Fase 4: aplicar ───────────────────────────────────────────────────
        # TODOS los nombres se apartan antes de escribir ninguno. `name` es único y durante
        # la sincronización conviven la fila vieja y la nueva: si se procesan de una en una,
        # la primera en tomar su nombre definitivo choca contra la fila que todavía no ha
        # sido procesada, y la operación entera se aborta. Vaciando el terreno primero, el
        # orden de proceso deja de importar.
        self._apartar_nombres(set(asignaciones.values()))
        self._liberar_nombres_en_conflicto(items, ids_de_siigo, reclamadas)

        synced = 0
        for item in items:
            name = str(item["name"]).strip()
            siigo_id = item.get("id")

            if siigo_id is None:
                model = self.db.query(Tax).filter(Tax.name == name).one_or_none()
                if model is None:
                    model = Tax(name=name)
                    self.db.add(model)
            else:
                siigo_id = int(siigo_id)
                model = self.db.query(Tax).filter(Tax.id == siigo_id).one_or_none()
                if model is None:
                    heredada = asignaciones.get(siigo_id)
                    if heredada is not None:
                        logger.info(
                            "Impuesto '%s': la fila local %s adopta el id %s de SIIGO",
                            name,
                            heredada,
                            siigo_id,
                        )
                        self._reidentificar(heredada, siigo_id)
                        model = self.db.query(Tax).filter(Tax.id == siigo_id).one()
                    else:
                        model = Tax(id=siigo_id, name=name)
                        self.db.add(model)

            model.name = name
            model.type = item["type"]
            model.percentage = Decimal(str(item.get("percentage", 0)))
            model.active = item.get("active", True)
            self.db.flush()
            synced += 1

        self.db.commit()
        self._realinear_secuencia()
        self._avisar_de_las_no_emparejadas(ids_de_siigo)
        return synced

    def _liberar_nombres_en_conflicto(
        self, items: list[dict], ids_de_siigo: set[int], reclamadas: set[int]
    ) -> None:
        """Aparta el nombre de las filas locales que no van a reidentificarse.

        Una fila local que sobrevive con su nombre puede estar ocupando el nombre que un
        impuesto de SIIGO necesita. No se borra —puede tener documentos apuntando a ella— ni
        se deja como está: se le añade un sufijo que la delata en el catálogo, para que quien
        lo revise vea que quedó fuera de la sincronización.
        """
        nombres_de_siigo = {_normalizar(str(item.get("name") or "")) for item in items}
        sobrantes = [
            fila
            for fila in self.db.query(Tax).all()
            if fila.id not in ids_de_siigo and fila.id not in reclamadas
        ]
        for fila in sobrantes:
            if _normalizar(fila.name) in nombres_de_siigo:
                logger.warning(
                    "Impuesto local %s ('%s') no existe en SIIGO y ocupaba un nombre suyo; "
                    "se aparta. Los documentos que lo usen seguirán siendo rechazados.",
                    fila.id,
                    fila.name,
                )
                fila.name = f"{fila.name} (local {fila.id})"[:100]
        self.db.flush()

    # ── Reidentificación de filas heredadas ────────────────────────────────────

    def _apartar_nombres(self, ids_locales: set) -> None:
        """Da un nombre provisional a las filas que están a punto de reidentificarse."""
        for id_local in ids_locales:
            self.db.execute(
                text("UPDATE integration_taxes SET name = :provisional WHERE id = :id"),
                {"provisional": f"__pend__{id_local}", "id": id_local},
            )
        self.db.flush()
        self.db.expire_all()

    def _buscar_por_nombre_exacto(
        self, item: dict, ids_de_siigo: set[int], reclamadas: set[int]
    ) -> Optional[int]:
        """Fila local con exactamente el mismo nombre, sin normalizar nada."""
        objetivo = str(item.get("name") or "").strip()
        for fila in self._candidatas(ids_de_siigo, reclamadas):
            if (fila.name or "").strip() == objetivo:
                return fila.id
        return None

    def _candidatas(self, ids_de_siigo: set[int], reclamadas: set[int]) -> list:
        """Filas que aún pueden reidentificarse.

        Nunca se ofrece una fila cuyo id ya sea un id de SIIGO: esa fila es correcta y
        pertenece a otro impuesto. Confundirlas reapuntaría documentos a un impuesto que no
        es el suyo, que es peor que el fallo que se está corrigiendo.
        """
        return [
            fila
            for fila in self.db.query(Tax).all()
            if fila.id not in ids_de_siigo and fila.id not in reclamadas
        ]

    def _buscar_por_nombre(
        self, item: dict, ids_de_siigo: set[int], reclamadas: set[int]
    ) -> Optional[int]:
        """Fila local con el mismo nombre, ignorando tildes, mayúsculas y puntos de cola."""
        objetivo = _normalizar(str(item.get("name") or ""))
        for fila in self._candidatas(ids_de_siigo, reclamadas):
            if _normalizar(fila.name) == objetivo:
                return fila.id
        return None

    def _buscar_por_tipo_y_porcentaje(
        self, item: dict, ids_de_siigo: set[int], reclamadas: set[int]
    ) -> Optional[int]:
        """Último recurso: el impuesto se reconoce por su naturaleza, no por su nombre.

        Cubre el caso del impuesto renombrado en SIIGO. Solo se aplica sobre las filas que
        ningún nombre reclamó, así que aquí ya no hay competencia posible.
        """
        tipo = str(item.get("type") or "").strip().lower()
        try:
            porcentaje = Decimal(str(item.get("percentage", 0)))
        except Exception:  # noqa: BLE001
            return None

        for fila in self._candidatas(ids_de_siigo, reclamadas):
            if (
                str(fila.type or "").strip().lower() == tipo
                and Decimal(str(fila.percentage or 0)) == porcentaje
            ):
                return fila.id
        return None

    def _reidentificar(self, id_local: int, id_siigo: int) -> None:
        """Cambia la clave de una fila y reapunta todo lo que la citaba.

        El orden es obligado: primero nace la fila con el id definitivo, después se mueven
        las referencias, y solo entonces desaparece la vieja. Al revés, la clave ajena
        rechazaría el movimiento o dejaría documentos apuntando a la nada.

        El nombre viaja con un valor provisional porque es único en la tabla y durante un
        instante conviven las dos filas. Quien llama le pone el definitivo al terminar.
        """
        self.db.flush()
        provisional = f"__sync__{id_siigo}"

        self.db.execute(
            text(
                "INSERT INTO integration_taxes "
                "(id, name, type, percentage, active, created_at, updated_at) "
                "SELECT :nuevo, :provisional, type, percentage, active, created_at, now() "
                "FROM integration_taxes WHERE id = :viejo"
            ),
            {"nuevo": id_siigo, "provisional": provisional, "viejo": id_local},
        )

        for tabla, columna in self._referencias():
            self.db.execute(
                # nosemgrep: avoid-sqlalchemy-text
                text(
                    # noqa justificado: `tabla`/`columna` salen de `_referencias()`, que los
                    # lee del catálogo de PostgreSQL — nunca de entrada de usuario. Los valores
                    # viajan como parámetros ligados.
                    f'UPDATE "{tabla}" SET "{columna}" = :nuevo WHERE "{columna}" = :viejo'  # noqa: S608
                ),
                {"nuevo": id_siigo, "viejo": id_local},
            )

        self.db.execute(
            text("DELETE FROM integration_taxes WHERE id = :viejo"), {"viejo": id_local}
        )
        # La sesión aún cree que la fila vieja existe; sin esto, el ORM la reescribiría al
        # confirmar y resucitaría la clave local que acabamos de retirar.
        self.db.expire_all()

    def _referencias(self) -> list[tuple[str, str]]:
        """Tablas y columnas que citan un impuesto del catálogo.

        Se buscan por DOS vías, y la segunda no es redundante: **en la base del cliente estas
        referencias no tienen clave ajena declarada**. `document_taxes.tax_id` es un entero
        suelto, sin `REFERENCES integration_taxes(id)`. Descubrirlas solo por el catálogo de
        claves ajenas —que es lo natural— no habría encontrado ninguna, y la reidentificación
        habría borrado la fila vieja dejando los documentos apuntando a un impuesto que ya no
        existe. Silenciosamente, y peor que el fallo que se venía a corregir.

        Por eso se añade la búsqueda por nombre de columna. En este esquema `tax_id` significa
        siempre «impuesto del catálogo de integración»; no hay un segundo catálogo con el que
        confundirlo.
        """
        encontradas: set[tuple[str, str]] = set()

        porFk = self.db.execute(
            text(
                """
                SELECT src.table_name, src.column_name
                FROM information_schema.referential_constraints rc
                JOIN information_schema.key_column_usage src
                  ON src.constraint_name = rc.constraint_name
                 AND src.constraint_schema = rc.constraint_schema
                JOIN information_schema.constraint_column_usage dst
                  ON dst.constraint_name = rc.unique_constraint_name
                 AND dst.constraint_schema = rc.unique_constraint_schema
                WHERE dst.table_name = 'integration_taxes'
                  AND dst.column_name = 'id'
                """
            )
        ).fetchall()
        encontradas.update((fila[0], fila[1]) for fila in porFk)

        porNombre = self.db.execute(
            text(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND column_name = 'tax_id'
                  AND table_name <> 'integration_taxes'
                """
            )
        ).fetchall()
        encontradas.update((fila[0], fila[1]) for fila in porNombre)

        return sorted(encontradas)

    def _realinear_secuencia(self) -> None:
        """Deja la secuencia por encima del mayor id, que ahora viene de SIIGO.

        Sin esto, la próxima fila creada localmente nacería con un id que SIIGO ya usa para
        otro impuesto, y el error volvería disfrazado: el envío no fallaría, contabilizaría
        con el impuesto equivocado.
        """
        try:
            self.db.execute(
                text(
                    "SELECT setval("
                    "  pg_get_serial_sequence('integration_taxes', 'id'),"
                    "  GREATEST((SELECT COALESCE(MAX(id), 0) FROM integration_taxes), 1)"
                    ")"
                )
            )
            self.db.commit()
        except Exception:  # noqa: BLE001
            # Un motor sin secuencias (SQLite en los tests) no necesita el realineado.
            self.db.rollback()

    def _avisar_de_las_no_emparejadas(self, ids_de_siigo: set[int]) -> None:
        """Deja constancia de las filas que SIIGO no reconoce.

        Una fila que sobrevive a la sincronización con su clave local es una bomba de
        relojería: no falla al guardarse, falla al contabilizar el primer documento que la
        use, y para entonces el rastro que la explica ya no está a la vista. Si un documento
        la cita, su envío será rechazado con `The id doesn't exist`.
        """
        if not ids_de_siigo:
            return
        sobrantes = [fila for fila in self.db.query(Tax).all() if fila.id not in ids_de_siigo]
        if sobrantes:
            logger.warning(
                "Impuestos sin correspondencia en SIIGO (%s): %s. Un documento que los use "
                "será rechazado con `The id doesn't exist`.",
                len(sobrantes),
                ", ".join(f"{fila.id}:{fila.name}" for fila in sobrantes),
            )

    def list(self, active: Optional[bool] = None) -> list[Tax]:
        query = self.db.query(Tax)
        if active is not None:
            query = query.filter(Tax.active.is_(active))
        return query.order_by(Tax.name.asc()).all()
