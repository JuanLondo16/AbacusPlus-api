from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint, func

from app.infrastructure.config.database import Base


class PaymentType(Base):
    __tablename__ = "integration_payment_types"
    __table_args__ = (UniqueConstraint("name", name="uq_payment_type_name"),)

    # Autoincrement real (igual que `Tax.id`), no `autoincrement=False`. Antes SOLO admitía el
    # id que trae SIIGO: como la importación por Excel nunca conoce ese id, cada fila intentaba
    # insertarse con `id=NULL` y Postgres la rechazaba por violar la restricción NOT NULL de la
    # llave primaria (invisible en los tests porque SQLite autoasigna un rowid ante un NULL en
    # una columna `INTEGER PRIMARY KEY`, sea o no `AUTOINCREMENT`). Con autoincrement real, un
    # tipo de pago creado localmente recibe un id propio; uno traído de SIIGO sigue
    # conservando el suyo (`PaymentType(id=siigo_id)` sigue funcionando igual que antes). Migrar
    # tenants ya aprovisionados requiere la migración en `internal.py` que agrega la secuencia.
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
