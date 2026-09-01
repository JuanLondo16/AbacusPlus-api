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
    # Solo las cuentas de último nivel (auxiliares) admiten movimiento; las de clase,
    # grupo, cuenta y subcuenta agrupan y no se pueden imputar. El dato lo calcula
    # integration-config-service al importar el Excel —detectando qué códigos son hoja— y
    # llega por la proyección. Se admite NULL porque las proyecciones anteriores a esta
    # columna no lo enviaban: quien valide debe tratar NULL como «no se sabe» y no como
    # «no imputable», para no invalidar catálogos ya cargados.
    accepts_movements = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
