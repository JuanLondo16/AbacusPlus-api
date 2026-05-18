from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, UniqueConstraint, func
from app.infrastructure.config.database import Base


class ChartAccount(Base):
    __tablename__ = "integration_chart_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "account_key", "code", name="uq_chart_account_provider_key_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, index=True)
    account_key = Column(String(120), nullable=False, default="default")
    external_id = Column(String(120), nullable=True, index=True)
    code = Column(String(80), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    account_type = Column(String(80), nullable=True)
    level = Column(Integer, nullable=True)
    parent_code = Column(String(80), nullable=True)
    accepts_movements = Column(Boolean, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
