from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone
from app.infrastructure.config.database import Base


class Issuer(Base):
    __tablename__ = "issuers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    nit = Column(String(50), unique=True, index=True, nullable=False)
    dv = Column(Integer, nullable=False)
    phone = Column(String(50), nullable=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    account_number = Column(String(50), nullable=True, default="")
    # Tipo de contribuyente / régimen (p.ej. "Responsable de IVA", "No responsable", etc.)
    tipo_contribuyente = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
