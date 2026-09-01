from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.services.retention_classification import classify
from app.infrastructure.persistence.models.retention import Retention

logger = logging.getLogger(__name__)

#: `type` se guarda SIEMPRE normalizado (minúsculas, sin tildes/puntuación) y no con la
#: grafía cruda de SIIGO ("ReteICA", "Retefuente"...), a diferencia de `integration_taxes`.
#: Es una decisión deliberada: la restricción única parcial de ReteICA compara
#: `type = 'reteica'` literalmente, y cada lector (xml-processor, llm-service) necesita saber
#: si una fila es ReteICA sin tener que reclasificar el texto libre en cada lectura. Se
#: normaliza UNA vez, al escribir.


class RetentionRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Lectura ──────────────────────────────────────────────────────────────
    def list(self, active: Optional[bool] = None, type: Optional[str] = None) -> list[Retention]:
        query = self.db.query(Retention)
        if active is not None:
            query = query.filter(Retention.active.is_(active))
        if type is not None:
            query = query.filter(Retention.type == (classify(type) or type))
        return query.order_by(Retention.type.asc(), Retention.name.asc()).all()

    def get_by_id(self, retention_id: int) -> Optional[Retention]:
        return self.db.query(Retention).filter(Retention.id == retention_id).one_or_none()

    # ── Sincronización SIIGO (ReteIVA / Retefuente / Autorretención) ──────────
    def upsert_siigo_many(self, items: Iterable[dict]) -> int:
        """Sincroniza retenciones desde SIIGO, conservando su `id` como clave.

        Igual motivo que `TaxRepository.upsert_many`: el `id` de SIIGO es el dato que viaja
        de vuelta al contabilizar (`retentions: [id,...]` en `POST /v1/purchases` para
        ReteIVA). Perder esa identidad rompe la contabilización con `The id doesn't exist`.

        A diferencia de `TaxRepository`, esta tabla es nueva y el backfill que la puebla
        (`retention_backfill.py`) YA preserva el id original de `integration_taxes` — que a
        su vez ya era el id real de SIIGO, reidentificado hace tiempo por `TaxRepository`.
        Por eso el camino común es sencillo: por `id` si ya existe, si no por `name` exacto
        (adopta el id de SIIGO reapuntando referencias, igual que `TaxRepository`), y solo si
        ninguno de los dos aplica, se crea con el id de SIIGO directamente. No reproduce las
        fases 2/3 (nombre normalizado, tipo+porcentaje) de `TaxRepository`: esa complejidad
        responde a años de imports duplicados sobre `integration_taxes` que esta tabla, al
        nacer ya separada y con `type` normalizado, no debería acumular. Si algún día lo
        hace, se puede portar el mismo patrón.

        ReteICA NUNCA llega por aquí: SIIGO no conoce municipios, así que el llamador debe
        filtrarla antes de invocar este método (ver `sync_siigo_taxes.py`).
        """
        synced = 0
        for item in items:
            siigo_id = item.get("id")
            name = str(item.get("name") or "").strip()
            clase = classify(item.get("type")) or classify(name)
            percentage = Decimal(str(item.get("percentage", 0)))
            active = item.get("active", True)

            if siigo_id is not None:
                siigo_id = int(siigo_id)
                model = self.db.query(Retention).filter(Retention.id == siigo_id).one_or_none()
                if model is None:
                    heredada = (
                        self.db.query(Retention)
                        .filter(Retention.type != "reteica", Retention.name == name)
                        .one_or_none()
                    )
                    if heredada is not None and heredada.id != siigo_id:
                        logger.info(
                            "Retención '%s': la fila local %s adopta el id %s de SIIGO",
                            name,
                            heredada.id,
                            siigo_id,
                        )
                        self._reidentificar(heredada.id, siigo_id)
                        model = (
                            self.db.query(Retention).filter(Retention.id == siigo_id).one()
                        )
                    else:
                        model = Retention(id=siigo_id, name=name, source="siigo")
                        self.db.add(model)
            else:
                model = (
                    self.db.query(Retention)
                    .filter(Retention.type != "reteica", Retention.name == name)
                    .one_or_none()
                )
                if model is None:
                    model = Retention(name=name, source="siigo")
                    self.db.add(model)

            model.name = name
            model.type = clase or str(item.get("type") or "").strip().lower()
            model.percentage = percentage
            model.active = active
            model.source = model.source or "siigo"
            self.db.flush()
            synced += 1

        self.db.commit()
        self._realinear_secuencia()
        return synced

    def _reidentificar(self, id_local: int, id_siigo: int) -> None:
        """Cambia la clave de una fila y reapunta todo lo que la citaba.

        Mismo patrón que `TaxRepository._reidentificar`. `document_taxes.tax_id` no lleva FK
        declarada (es un entero suelto), así que las referencias se descubren por nombre de
        columna y no solo por el catálogo de claves ajenas.
        """
        self.db.flush()
        provisional = f"__sync__{id_siigo}"
        self.db.execute(
            text(
                "INSERT INTO integration_retentions "
                "(id, name, type, percentage, active, municipality_code, municipality_name, "
                " retention_concept, minimum_base_uvt, source, created_at, updated_at) "
                "SELECT :nuevo, :provisional, type, percentage, active, municipality_code, "
                "       municipality_name, retention_concept, minimum_base_uvt, source, "
                "       created_at, now() "
                "FROM integration_retentions WHERE id = :viejo"
            ),
            {"nuevo": id_siigo, "provisional": provisional, "viejo": id_local},
        )
        for tabla, columna in self._referencias():
            self.db.execute(
                # nosemgrep: avoid-sqlalchemy-text
                text(
                    f'UPDATE "{tabla}" SET "{columna}" = :nuevo WHERE "{columna}" = :viejo'  # noqa: S608
                ),
                {"nuevo": id_siigo, "viejo": id_local},
            )
        self.db.execute(
            text("DELETE FROM integration_retentions WHERE id = :viejo"), {"viejo": id_local}
        )
        self.db.expire_all()

    def _referencias(self) -> list[tuple[str, str]]:
        """Columnas `tax_id` de la base del tenant, salvo los catálogos mismos.

        `document_taxes.tax_id` no declara FK; se descubre por nombre de columna, igual que
        `TaxRepository._referencias()` — ambos catálogos comparten esa misma columna.
        """
        try:
            filas = self.db.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND column_name = 'tax_id' "
                    "AND table_name NOT IN ('integration_taxes', 'integration_retentions')"
                )
            ).fetchall()
            return sorted((f[0], f[1]) for f in filas)
        except Exception:  # noqa: BLE001 — SQLite (tests) no tiene information_schema.
            return [("document_taxes", "tax_id"), ("document_details", "tax_id")]

    def _realinear_secuencia(self) -> None:
        try:
            self.db.execute(
                text(
                    "SELECT setval("
                    "  pg_get_serial_sequence('integration_retentions', 'id'),"
                    "  GREATEST((SELECT COALESCE(MAX(id), 0) FROM integration_retentions), 1)"
                    ")"
                )
            )
            self.db.commit()
        except Exception:  # noqa: BLE001 — SQLite (tests) no tiene secuencias.
            self.db.rollback()

    # ── Importación de Excel (municipios de ReteICA) ──────────────────────────
    def upsert_ica_rows(self, rows: Iterable[dict], *, replace: bool = False) -> int:
        """Carga tarifas de ReteICA por municipio. Idéntica semántica de `replace` que ya
        usaba `retention_ica_rates` en xml-processor: `False` hace upsert por
        (municipio, concepto); `True` reemplaza solo las filas `type='reteica'` (nunca toca
        retefuente/reteiva/autorretencion, que vienen de SIIGO).
        """
        rows = list(rows)
        if replace:
            self.db.query(Retention).filter(Retention.type == "reteica").delete(
                synchronize_session=False
            )
            self.db.flush()

        count = 0
        for row in rows:
            code = str(row["municipality_code"]).strip()
            concept = str(row.get("retention_concept") or "todos").strip().lower()
            existing = (
                self.db.query(Retention)
                .filter(
                    Retention.type == "reteica",
                    Retention.municipality_code == code,
                    Retention.retention_concept == concept,
                )
                .one_or_none()
            )
            nombre = f"ReteICA {row.get('municipality_name') or code} · {concept}"[:150]
            if existing is None:
                self.db.add(
                    Retention(
                        name=nombre,
                        type="reteica",
                        percentage=Decimal(str(row["percentage"])),
                        active=True,
                        municipality_code=code,
                        municipality_name=row.get("municipality_name"),
                        retention_concept=concept,
                        minimum_base_uvt=row.get("minimum_base_uvt"),
                        source="excel",
                    )
                )
            else:
                existing.name = nombre
                existing.percentage = Decimal(str(row["percentage"]))
                existing.municipality_name = row.get("municipality_name")
                existing.minimum_base_uvt = row.get("minimum_base_uvt")
                existing.active = True
            count += 1
        self.db.commit()
        return count
