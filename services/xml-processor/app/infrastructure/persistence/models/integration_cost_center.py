from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint

from app.infrastructure.config.database import Base


class IntegrationCostCenter(Base):
    """Stub local de integration_cost_centers — tabla gestionada por integration-config-service."""

    __tablename__ = "integration_cost_centers"
    __table_args__ = (UniqueConstraint("code", name="uq_cost_center_code"),)

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(120), nullable=True)
    code = Column(String(80), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
