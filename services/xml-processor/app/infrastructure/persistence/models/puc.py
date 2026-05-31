from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint

from app.infrastructure.config.database import Base


class PucAccount(Base):
    __tablename__ = "puc_accounts"
    __table_args__ = (UniqueConstraint("code", name="uq_puc_accounts_code"),)

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), nullable=False, index=True)  # código PUC
    name = Column(String(200), nullable=False)
    level = Column(Integer, nullable=True)  # opcional: nivel (1-6) si se quiere usar
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
