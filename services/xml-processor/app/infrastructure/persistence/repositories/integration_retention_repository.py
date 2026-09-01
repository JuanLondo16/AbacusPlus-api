from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.integration_retention import IntegrationRetention


class IntegrationRetentionRepository:
    """Lectura del catálogo de retenciones (ReteICA, ReteIVA, Retefuente, Autorretención)
    sincronizado/importado por integration-config-service. Mismo contrato que
    `IntegrationTaxRepository`, para poder usarse indistintamente donde solo se necesita
    `id`/`name`/`type`/`active` (p. ej. `AccountingKnowledgePublisher`)."""

    def __init__(self, db: Session):
        self._db = db

    def get_active(self) -> list[IntegrationRetention]:
        return (
            self._db.query(IntegrationRetention)
            .filter(IntegrationRetention.active.is_(True))
            .order_by(IntegrationRetention.name)
            .all()
        )

    def get_by_id(self, retention_id: int) -> "IntegrationRetention | None":
        return (
            self._db.query(IntegrationRetention)
            .filter(IntegrationRetention.id == retention_id)
            .one_or_none()
        )
