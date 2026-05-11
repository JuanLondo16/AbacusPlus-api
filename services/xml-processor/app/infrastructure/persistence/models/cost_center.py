from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint

from app.infrastructure.config.database import Base


class CostCenter(Base):
    __tablename__ = "cost_centers"
    __table_args__ = (
        UniqueConstraint("code", name="uq_cost_centers_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

