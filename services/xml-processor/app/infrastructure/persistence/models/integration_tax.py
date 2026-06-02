from sqlalchemy import Boolean, Column, Integer, Numeric, String

from app.infrastructure.config.database import Base


class IntegrationTax(Base):
    """Stub local de integration_taxes — tabla gestionada por integration-config-service."""

    __tablename__ = "integration_taxes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    type = Column(String(50), nullable=False)
    percentage = Column(Numeric(10, 4), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
