from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, UniqueConstraint, func

from app.infrastructure.config.database import Base


class Product(Base):
    __tablename__ = "integration_products"
    __table_args__ = (UniqueConstraint("code", name="uq_product_code"),)

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(80), nullable=False, index=True)
    type = Column(String(20), nullable=False)
    description = Column(String(500), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
