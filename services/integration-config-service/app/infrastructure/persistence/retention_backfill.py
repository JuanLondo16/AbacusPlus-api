"""Backfill ÚNICO: separa `integration_taxes` en impuestos y retenciones (2026-08-31).

Contexto completo en el informe de la migración. En una frase: hasta ahora las 4
retenciones (ReteICA, ReteIVA, Retefuente, Autorretención) vivían mezcladas con los
impuestos reales del documento (IVA, Impoconsumo, AdValorem) en `integration_taxes`, y el
ReteICA por municipio vivía ADEMÁS en una tabla paralela del xml-processor
(`retention_ica_rates`) casi nunca coincidente en porcentaje con las tarifas genéricas
sincronizadas de SIIGO. `run()` mueve las retenciones a `integration_retentions` (que ya
fusiona el municipio/concepto/base mínima de ReteICA en la misma fila) y reapunta
`document_taxes`/`document_details` al nuevo id.

Diseño de seguridad — se ejecuta sobre datos reales de un tenant:

1. **Preserva el id original siempre que puede.** Los ids que hoy tiene una fila de
   retención en `integration_taxes` YA SON los ids reales de SIIGO (los reidentificó
   `TaxRepository` hace tiempo). Reutilizarlos en `integration_retentions` significa que
   `document_taxes.tax_id` **no necesita cambiar en el caso común** — y, más importante,
   que la retención sigue siendo enviable a SIIGO al contabilizar sin haber perdido su
   identidad. Solo si ese id ya está ocupado en `integration_retentions` (colisión con una
   fila de ReteICA migrada antes, o con otra retención) se genera uno nuevo y se registra en
   el mapa de reemplazo — por eso el mapa existe, aunque en el caso común quede vacío.
2. **Todo en una transacción.** Si algo falla a mitad de camino, Postgres deshace la
   transacción entera: nunca queda un estado a medias (filas copiadas sin reapuntar, o
   borradas sin haberse copiado antes).
3. **Idempotente.** Correrlo dos veces no duplica nada: las filas de `integration_taxes` ya
   migradas se identifican por ausencia (se borran al final de una corrida exitosa, así que
   una segunda corrida no encuentra nada que migrar); las de `retention_ica_rates` se
   identifican por existencia previa en `integration_retentions` (mismo municipio+concepto).
4. **Nunca borra a ciegas.** Antes de eliminar una fila de `integration_taxes`, se comprueba
   que ninguna referencia conocida (`document_details.tax_id`, que SÍ lleva FK a
   `integration_taxes`) siga sin poder reapuntarse. Si algo no cuadra, se deja la fila
   original SIN BORRAR y se registra en el reporte — nunca se fuerza el borrado ni se corrige
   en silencio.
5. **Los huérfanos se reportan, no se inventan.** Un `tax_id` que no resuelve en ningún
   catálogo tras la migración (dato ya corrupto de antes, sin relación con este backfill) se
   lista en el reporte para revisión manual.
6. **Las tarifas GENÉRICAS de ReteICA (sin municipio) migran DESACTIVADAS.** Las filas que
   `integration_taxes` traía como "ReteICA 6.9" (solo porcentaje, sin poder verificarse
   contra ningún municipio) son precisamente el dato que motivó esta migración. Se copian
   igual — un `document_taxes` existente puede citarlas y no puede perder su nombre ni su
   tarifa — pero con `active=false`: no pueden volver a ofrecerse como opción nueva, ni al
   contador en el selector ni al modelo de IA. Las filas de ReteICA verificables (con
   municipio, concepto y base mínima) son las que aporta `retention_ica_rates` en el paso
   siguiente, y esas sí quedan activas.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.domain.services.retention_classification import RETENTION_TYPES, classify

logger = logging.getLogger(__name__)

#: Columnas `tax_id` conocidas de antemano. `document_details.tax_id` lleva FK declarada a
#: `integration_taxes(id)` — reapuntarla a un id que solo existe en `integration_retentions`
#: la rompería, así que se trata aparte (ver `_FK_COLUMNS`). `document_taxes.tax_id` no lleva
#: FK (es un entero suelto), que es precisamente el motivo original de este trabajo.
_PLAIN_REFERENCE_COLUMNS: tuple[tuple[str, str], ...] = (("document_taxes", "tax_id"),)
_FK_REFERENCE_COLUMNS: tuple[tuple[str, str], ...] = (("document_details", "tax_id"),)


@dataclass
class BackfillReport:
    taxes_scanned: int = 0
    taxes_migrated: int = 0
    taxes_reused_id: int = 0
    taxes_remapped_id: int = 0
    ica_rates_scanned: int = 0
    ica_rates_migrated: int = 0
    ica_rates_already_present: int = 0
    references_updated: dict[str, int] = field(default_factory=dict)
    taxes_deleted: int = 0
    taxes_kept_due_to_reference: list[dict[str, Any]] = field(default_factory=list)
    orphans: list[dict[str, Any]] = field(default_factory=list)
    other_tax_id_columns_found: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "taxes_scanned": self.taxes_scanned,
            "taxes_migrated": self.taxes_migrated,
            "taxes_reused_id": self.taxes_reused_id,
            "taxes_remapped_id": self.taxes_remapped_id,
            "ica_rates_scanned": self.ica_rates_scanned,
            "ica_rates_migrated": self.ica_rates_migrated,
            "ica_rates_already_present": self.ica_rates_already_present,
            "references_updated": self.references_updated,
            "taxes_deleted": self.taxes_deleted,
            "taxes_kept_due_to_reference": self.taxes_kept_due_to_reference,
            "orphans": self.orphans,
            "other_tax_id_columns_found": self.other_tax_id_columns_found,
        }


def _table_exists(conn, name: str) -> bool:
    from sqlalchemy import inspect

    try:
        return inspect(conn).has_table(name)
    except Exception:  # noqa: BLE001
        return False


def run(engine: Engine) -> BackfillReport:
    report = BackfillReport()

    with engine.begin() as conn:
        # ── 1. integration_taxes -> integration_retentions ────────────────────
        tax_rows = conn.execute(
            text("SELECT id, name, type, percentage, active FROM integration_taxes ORDER BY id")
        ).mappings().all()
        report.taxes_scanned = len(tax_rows)

        migrable = [r for r in tax_rows if classify(r["type"]) in RETENTION_TYPES]
        old_to_new: dict[int, int] = {}

        # Ids ya ocupados en integration_retentions (por una fila de ICA insertada en una
        # corrida anterior, por ejemplo), para saber si el id original puede preservarse.
        ids_ocupados = {
            row[0]
            for row in conn.execute(text("SELECT id FROM integration_retentions")).fetchall()
        }

        for row in migrable:
            tipo = classify(row["type"]) or str(row["type"]).lower()
            if tipo == "reteica":
                # Es una de las tarifas GENÉRICAS de ReteICA que traía integration_taxes (p.
                # ej. "ReteICA 6.9"), sin municipio ni concepto: exactamente el dato que
                # motivó esta migración porque casi nunca coincidía en porcentaje con la
                # tarifa real de un municipio. Se migra igualmente — algún document_taxes
                # existente puede apuntarle y no puede perder su nombre — pero se DESACTIVA:
                # no puede ofrecerse como opción nueva (ni al contador ni a la IA) sin
                # municipio con el que verificarla. Las filas de ReteICA verificables son
                # las que trae `retention_ica_rates` (paso siguiente), siempre activas.
                activa = False
                origen = "migracion_integration_taxes_reteica_generica"
            else:
                activa = row["active"]
                origen = "migracion_integration_taxes"

            if row["id"] in ids_ocupados:
                # El id original ya lo tiene otra fila (colisión, poco probable pero posible):
                # se preserva la SEGURIDAD (nunca se sobreescribe una fila ajena) sobre la
                # preservación del id, y se deja constancia en el mapa de reemplazo.
                new_id = conn.execute(
                    text(
                        "INSERT INTO integration_retentions "
                        "(name, type, percentage, active, source, created_at, updated_at) "
                        "VALUES (:name, :type, :percentage, :active, :source, now(), now()) "
                        "RETURNING id"
                    ),
                    {
                        "name": row["name"],
                        "type": tipo,
                        "percentage": row["percentage"],
                        "active": activa,
                        "source": origen,
                    },
                ).scalar_one()
                old_to_new[row["id"]] = new_id
                report.taxes_remapped_id += 1
                logger.warning(
                    "Backfill retenciones: el id %s de integration_taxes ('%s') ya existía "
                    "en integration_retentions; se le asignó el id nuevo %s.",
                    row["id"],
                    row["name"],
                    new_id,
                )
            else:
                conn.execute(
                    text(
                        "INSERT INTO integration_retentions "
                        "(id, name, type, percentage, active, source, created_at, updated_at) "
                        "VALUES (:id, :name, :type, :percentage, :active, :source, now(), now())"
                    ),
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "type": tipo,
                        "percentage": row["percentage"],
                        "active": activa,
                        "source": origen,
                    },
                )
                old_to_new[row["id"]] = row["id"]
                ids_ocupados.add(row["id"])
                report.taxes_reused_id += 1
            report.taxes_migrated += 1

        # La secuencia de integration_retentions debe quedar por encima del mayor id, ya sean
        # preservados o nuevos: si no, la próxima fila creada localmente (p. ej. una tarifa de
        # ReteICA importada por Excel) podría nacer con un id que ya usa una retención migrada.
        _realinear_secuencia(conn)

        # ── 2. retention_ica_rates -> integration_retentions (type='reteica') ─
        ica_rows = []
        if _table_exists(conn, "retention_ica_rates"):
            ica_rows = conn.execute(
                text("SELECT * FROM retention_ica_rates ORDER BY id")
            ).mappings().all()
        report.ica_rates_scanned = len(ica_rows)

        for row in ica_rows:
            code = str(row["municipality_code"]).strip()
            concept = str(row["retention_concept"] or "todos").strip().lower()
            existente = conn.execute(
                text(
                    "SELECT id FROM integration_retentions WHERE type = 'reteica' "
                    "AND municipality_code = :code AND retention_concept = :concept"
                ),
                {"code": code, "concept": concept},
            ).first()
            if existente:
                report.ica_rates_already_present += 1
                continue
            nombre = f"ReteICA {row['municipality_name'] or code} · {concept}"[:150]
            conn.execute(
                text(
                    "INSERT INTO integration_retentions "
                    "(name, type, percentage, active, municipality_code, municipality_name, "
                    " retention_concept, minimum_base_uvt, source, created_at, updated_at) "
                    "VALUES (:name, 'reteica', :percentage, true, :code, :mname, :concept, "
                    ":base, 'migracion_retention_ica_rates', now(), now())"
                ),
                {
                    "name": nombre,
                    "percentage": row["percentage"],
                    "code": code,
                    "mname": row["municipality_name"],
                    "concept": concept,
                    "base": row["minimum_base_uvt"],
                },
            )
            report.ica_rates_migrated += 1

        _realinear_secuencia(conn)

        # ── 3. Reapuntar referencias conocidas ─────────────────────────────────
        bloqueados: dict[int, list[str]] = {}
        for tabla, columna in _PLAIN_REFERENCE_COLUMNS:
            if not _table_exists(conn, tabla):
                continue
            for old_id, new_id in old_to_new.items():
                if old_id == new_id:
                    continue  # id preservado: nada que reapuntar en este par.
                resultado = conn.execute(
                    text(f'UPDATE "{tabla}" SET "{columna}" = :new WHERE "{columna}" = :old'),
                    {"new": new_id, "old": old_id},
                )
                if resultado.rowcount:
                    clave = f"{tabla}.{columna}"
                    report.references_updated[clave] = (
                        report.references_updated.get(clave, 0) + resultado.rowcount
                    )

        for tabla, columna in _FK_REFERENCE_COLUMNS:
            if not _table_exists(conn, tabla):
                continue
            for old_id, new_id in old_to_new.items():
                if old_id == new_id:
                    continue
                # Esta columna SÍ lleva FK a integration_taxes(id): reapuntarla a un id que
                # solo existe en integration_retentions rompería la integridad referencial.
                # No debería ocurrir nunca (los impuestos de línea son siempre IVA/Impoconsumo/
                # AdValorem, nunca una retención), pero si alguna fila lo hiciera, se protege
                # el id viejo en vez de corromper la referencia o fallar toda la migración.
                afectadas = conn.execute(
                    text(f'SELECT count(*) FROM "{tabla}" WHERE "{columna}" = :old'),
                    {"old": old_id},
                ).scalar_one()
                if afectadas:
                    bloqueados.setdefault(old_id, []).append(f"{tabla}.{columna}")

        # Barrido best-effort (solo Postgres) de columnas `tax_id` no contempladas arriba,
        # para reportarlas y que alguien las revise — nunca se tocan automáticamente.
        try:
            extra = conn.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND column_name = 'tax_id' "
                    "AND table_name NOT IN ('integration_taxes', 'integration_retentions')"
                )
            ).fetchall()
            conocidas = {t for t, _ in _PLAIN_REFERENCE_COLUMNS} | {
                t for t, _ in _FK_REFERENCE_COLUMNS
            }
            for tabla, columna in extra:
                if tabla not in conocidas:
                    report.other_tax_id_columns_found.append(f"{tabla}.{columna}")
        except Exception:  # noqa: BLE001 — SQLite (tests): sin information_schema.
            pass

        # ── 4. Huérfanos: tax_id que no resuelven en NINGÚN catálogo ───────────
        catalogo_valido = {
            r["id"] for r in tax_rows if r["id"] not in old_to_new
        } | set(old_to_new.values())
        for tabla, columna in _PLAIN_REFERENCE_COLUMNS + _FK_REFERENCE_COLUMNS:
            if not _table_exists(conn, tabla):
                continue
            valores = conn.execute(
                text(f'SELECT DISTINCT "{columna}" FROM "{tabla}" WHERE "{columna}" IS NOT NULL')
            ).fetchall()
            for (valor,) in valores:
                if valor in catalogo_valido or valor in old_to_new:
                    continue
                report.orphans.append({"table": tabla, "column": columna, "tax_id": valor})

        if report.orphans:
            logger.warning(
                "Backfill retenciones: %d referencias huérfanas (no se tocan, quedan para "
                "revisión manual): %s",
                len(report.orphans),
                report.orphans,
            )

        # ── 5. Borrar de integration_taxes solo lo migrado y sin bloqueos ──────
        for old_id in old_to_new:
            if old_id in bloqueados:
                report.taxes_kept_due_to_reference.append(
                    {"id": old_id, "blocked_by": bloqueados[old_id]}
                )
                logger.warning(
                    "integration_taxes id=%s no se elimina: todavía lo referencia %s.",
                    old_id,
                    bloqueados[old_id],
                )
                continue
            conn.execute(text("DELETE FROM integration_taxes WHERE id = :id"), {"id": old_id})
            report.taxes_deleted += 1

    return report


def _realinear_secuencia(conn) -> None:
    try:
        conn.execute(
            text(
                "SELECT setval("
                "  pg_get_serial_sequence('integration_retentions', 'id'),"
                "  GREATEST((SELECT COALESCE(MAX(id), 0) FROM integration_retentions), 1)"
                ")"
            )
        )
    except Exception:  # noqa: BLE001 — SQLite (tests): sin secuencias.
        pass
