from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.integration_tax import IntegrationTax


class IntegrationTaxRepository:
    """Lectura del catálogo de impuestos/retenciones sincronizado desde SIIGO."""

    def __init__(self, db: Session):
        self._db = db

    def get_active(self) -> list[IntegrationTax]:
        return (
            self._db.query(IntegrationTax)
            .filter(IntegrationTax.active.is_(True))
            .order_by(IntegrationTax.name)
            .all()
        )

    def get_by_id(self, tax_id: int) -> "IntegrationTax | None":
        """Devuelve la retención del catálogo por id, activa o no.

        Permite validar la pertenencia de un solo id —y distinguir «no existe» de «existe
        pero está inactiva»— sin traer todo el catálogo. Es el mismo criterio que usa RF-01
        con el PUC y RF-07 con los centros de costo.
        """
        return self._db.query(IntegrationTax).filter(IntegrationTax.id == tax_id).one_or_none()
