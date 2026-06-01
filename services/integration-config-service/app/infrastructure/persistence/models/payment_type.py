from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint, func

from app.infrastructure.config.database import Base


class PaymentType(Base):
    __tablename__ = "integration_payment_types"
    __table_args__ = (UniqueConstraint("name", name="uq_payment_type_name"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
