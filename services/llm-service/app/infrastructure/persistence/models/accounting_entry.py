from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text, JSON

from app.infrastructure.config.database import Base


class AccountingEntry(Base):
    __tablename__ = "accounting_entries"

    id               = Column(Integer, primary_key=True, index=True)
    document_id      = Column(Integer, nullable=False, index=True)
    system_prompt_id = Column(Integer, nullable=True)
    entries          = Column(JSON, nullable=True)        # List[dict] — líneas del asiento
    model_used       = Column(String(50), nullable=True)
    status           = Column(String(20), nullable=False)  # generated | error
    error_message    = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
