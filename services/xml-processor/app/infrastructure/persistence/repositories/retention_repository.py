from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.retention_fuente import RetentionFuenteRate
from app.infrastructure.persistence.models.retention_ica import RetentionIcaRate


class RetentionRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_fuente_rates(self) -> list[RetentionFuenteRate]:
        return (
            self._db.query(RetentionFuenteRate)
            .order_by(RetentionFuenteRate.retention_concept, RetentionFuenteRate.taxpayer_type)
            .all()
        )

    def get_ica_rates(self) -> list[RetentionIcaRate]:
        return self._db.query(RetentionIcaRate).order_by(RetentionIcaRate.municipality_code).all()
