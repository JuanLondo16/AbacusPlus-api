"""`document_taxes.tax_id` puede apuntar a `integration_taxes` O a `integration_retentions`.

La mayoría de las filas de `document_taxes` son retenciones (RF-02: ReteFuente, ReteICA,
ReteIVA, Autorretención), pero el catálogo real del cliente también registra ahí impuestos
del propio documento — Impoconsumo, por ejemplo, para conciliarlo — así que la validación de
un `tax_id` no puede asumir una sola tabla. Antes de la migración de 2026-08-31 ambas cosas
vivían en `integration_taxes`; ahora viven separadas, y esta clase es el punto único que las
combina para las rutas que no saben (ni necesitan saber) de cuál de las dos viene un id.

Las rutas que SÍ saben qué buscan (`document_details.tax_id`, que solo puede ser un impuesto
de línea) siguen usando `IntegrationTaxRepository` directamente: mezclarlas ahí no aporta
nada y solo abre la puerta a que una retención se cuele donde no debe ir.
"""

from typing import Optional

from app.infrastructure.persistence.repositories.integration_retention_repository import (
    IntegrationRetentionRepository,
)
from app.infrastructure.persistence.repositories.integration_tax_repository import (
    IntegrationTaxRepository,
)


class TaxOrRetentionRepository:
    def __init__(self, db):
        self._taxes = IntegrationTaxRepository(db)
        self._retentions = IntegrationRetentionRepository(db)

    def get_by_id(self, tax_id: int) -> Optional[object]:
        """Busca primero en impuestos y luego en retenciones — ninguno de los dos catálogos
        comparte rango de ids con el otro (cada uno tiene su propia secuencia), así que el
        orden no puede producir un falso emparejamiento."""
        item = self._taxes.get_by_id(tax_id)
        if item is not None:
            return item
        return self._retentions.get_by_id(tax_id)

    def get_active(self) -> list:
        return [*self._taxes.get_active(), *self._retentions.get_active()]
