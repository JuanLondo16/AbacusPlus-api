from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, UniqueConstraint, func
from app.infrastructure.config.database import Base


class CostCenter(Base):
    __tablename__ = "integration_cost_centers"
    __table_args__ = (
        UniqueConstraint("provider", "account_key", "code", name="uq_cost_center_provider_key_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, index=True)
    account_key = Column(String(120), nullable=False, default="default")
    external_id = Column(String(120), nullable=True, index=True)
    code = Column(String(80), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
