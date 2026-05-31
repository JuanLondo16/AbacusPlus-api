from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.infrastructure.config.database import Base


class Tax(Base):
    __tablename__ = "taxes"

    id = Column(Integer, primary_key=True, index=True)
    receiver_nit = Column(String(50), nullable=False)
    tax = Column(String(50), nullable=False)
    percentage = Column(Float, nullable=False)
    account_number = Column(String(50), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
