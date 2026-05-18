from sqlalchemy import Boolean, Column, Integer, String
from app.infrastructure.config.database import Base


class IntegrationChartAccount(Base):
    __tablename__ = "integration_chart_accounts"

    id               = Column(Integer, primary_key=True, index=True)
    provider         = Column(String(50), nullable=False, index=True)
    account_key      = Column(String(100), nullable=False, index=True)
    code             = Column(String(20), nullable=False, index=True)
    name             = Column(String(200), nullable=False)
    account_type     = Column(String(50), nullable=True)
    level            = Column(Integer, nullable=True)
    parent_code      = Column(String(20), nullable=True)
    accepts_movements = Column(Boolean, nullable=True, default=True)
    active           = Column(Boolean, nullable=False, default=True)
