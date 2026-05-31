from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String, UniqueConstraint

from app.infrastructure.config.database import Base


class RetentionFuenteRate(Base):
    __tablename__ = "retention_fuente_rates"
    __table_args__ = (
        UniqueConstraint(
            "retention_concept", "taxpayer_type", name="uq_retention_fuente_concept_taxpayer"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    retention_concept = Column(String(200), nullable=False, index=True)
    taxpayer_type = Column(String(100), nullable=False, index=True)
    minimum_base_uvt = Column(Numeric(10, 2), nullable=True)
    minimum_base_pesos = Column(Numeric(15, 2), nullable=True)
    rate_percentage = Column(Numeric(10, 6), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
