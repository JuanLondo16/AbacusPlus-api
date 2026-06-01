from sqlalchemy import Boolean, Column, Integer, String

from app.infrastructure.config.database import Base


class IntegrationPaymentType(Base):
    __tablename__ = "integration_payment_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
