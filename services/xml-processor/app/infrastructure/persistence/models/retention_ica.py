from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String, UniqueConstraint

from app.infrastructure.config.database import Base


class RetentionIcaRate(Base):
    __tablename__ = "retention_ica_rates"
    __table_args__ = (
        UniqueConstraint("municipality_code", name="uq_retention_ica_municipality_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    municipality_code = Column(String(20), nullable=False, index=True)  # DANE u otro
    municipality_name = Column(String(120), nullable=True)
    # Porcentaje en términos de % (ej 0.966 => 0.966%)
    percentage = Column(Numeric(10, 6), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

