from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime, timezone
from app.infrastructure.config.database import Base
from sqlalchemy.ext.hybrid import hybrid_property


class Issuer(Base):
    __tablename__ = "issuers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    nit = Column(String(50), unique=True, index=True, nullable=False)
    dv = Column(Integer, nullable=False)
    phone = Column(String(50), nullable=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    account_number = Column(String(50), nullable=True, default="")
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
