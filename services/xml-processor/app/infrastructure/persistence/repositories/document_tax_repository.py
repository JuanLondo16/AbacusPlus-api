from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.application.dto.document_tax import compute_retention_value
from app.infrastructure.persistence.models.document_tax import DocumentTax

# RF-08: valores admitidos para el origen de una retención.
_VALID_SOURCES = frozenset({"llm", "manual"})


def _normalized_source(source: Optional[str]) -> str:
    """Acota el origen a los valores permitidos.

    El valor lo declara el cliente, así que se valida en vez de persistirlo tal cual:
    cualquier cosa distinta de `llm` se registra como `manual`, que es el caso por defecto
    y el más conservador (asume trabajo del contador y por tanto advierte antes de pisarlo).
    """
    value = (source or "").strip().lower()
    return value if value in _VALID_SOURCES else "manual"


class DocumentTaxRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_document(self, document_id: int) -> list[DocumentTax]:
        return (
            self.db.query(DocumentTax)
            .filter(DocumentTax.document_id == document_id)
            .order_by(DocumentTax.id)
            .all()
        )

    def get(self, document_id: int, document_tax_id: int) -> Optional[DocumentTax]:
        return (
            self.db.query(DocumentTax)
            .filter(
                DocumentTax.id == document_tax_id,
                DocumentTax.document_id == document_id,
            )
            .first()
        )

    def _tipo_de_retencion(self, tax_id: Optional[int]) -> Optional[str]:
        """Tipo del impuesto/retención en el catálogo, que decide cómo se lee su tarifa.

        Hace falta porque el ICA se publica por mil y el resto en porcentaje: sin el tipo, la
        misma cifra —7,66— significa dos cosas que se diferencian en un factor de diez sobre
        dinero de un tercero.

        `tax_id` puede resolver en `integration_taxes` (impuestos) o en
        `integration_retentions` (retenciones, desde la migración del 2026-08-31) — se
        consultan las dos, porque este método no sabe de antemano cuál de las dos citó
        `document_taxes.tax_id`. Si ninguna resuelve, o si `integration_retentions` todavía
        no existe en una base sin migrar, se devuelve None y el cálculo usa el divisor de
        siempre: es preferible mantener el comportamiento conocido a inventar uno ante un
        fallo de lectura.
        """
        if not tax_id:
            return None
        try:
            fila = self.db.execute(
                text(
                    "SELECT type FROM integration_taxes WHERE id = :id "
                    "UNION ALL "
                    "SELECT type FROM integration_retentions WHERE id = :id "
                    "LIMIT 1"
                ),
                {"id": int(tax_id)},
            ).first()
        except Exception:  # noqa: BLE001
            return None
        return fila[0] if fila else None

    def create(
        self,
        document_id: int,
        tax_id: int,
        taxable_base: float,
        percentage: float,
        source: Optional[str] = None,
    ) -> DocumentTax:
        row = DocumentTax(
            document_id=document_id,
            tax_id=tax_id,
            taxable_base=taxable_base,
            percentage=percentage,
            value=compute_retention_value(
                taxable_base, percentage, self._tipo_de_retencion(tax_id)
            ),
            source=_normalized_source(source),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(
        self,
        document_id: int,
        document_tax_id: int,
        tax_id: Optional[int] = None,
        taxable_base: Optional[float] = None,
        percentage: Optional[float] = None,
    ) -> Optional[DocumentTax]:
        row = self.get(document_id, document_tax_id)
        if row is None:
            return None
        if tax_id is not None:
            row.tax_id = tax_id
        if taxable_base is not None:
            row.taxable_base = taxable_base
        if percentage is not None:
            row.percentage = percentage
        # El valor retenido siempre deriva de base × tarifa (nunca se envía directo), y el
        # divisor lo fija el tipo: por mil en ReteICA, porcentaje en el resto.
        row.value = compute_retention_value(
            row.taxable_base, row.percentage, self._tipo_de_retencion(row.tax_id)
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, document_id: int, document_tax_id: int) -> bool:
        row = self.get(document_id, document_tax_id)
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True
