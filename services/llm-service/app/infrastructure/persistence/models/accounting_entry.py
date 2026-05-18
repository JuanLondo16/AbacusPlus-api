from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.infrastructure.config.database import Base


class AccountingEntry(Base):
    __tablename__ = "accounting_entries"

    id               = Column(Integer, primary_key=True, index=True)
    source_id        = Column(Integer, unique=True, nullable=True, index=True)
    document_id      = Column(Integer, nullable=True, index=True)
    source           = Column(String(10), nullable=True, default="llm")
    issuer_nit       = Column(String(20), nullable=True, index=True)
    issuer_name      = Column(String(200), nullable=True)
    system_prompt_id = Column(Integer, nullable=True)
    model_used       = Column(String(50), nullable=True)
    status           = Column(String(20), nullable=True)
    error_message    = Column(Text, nullable=True)
    rag_context      = Column(JSON, nullable=True)
    created_at       = Column("extracted_at", DateTime, default=datetime.utcnow)

    lines = relationship(
        "AccountingEntryLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="AccountingEntryLine.id",
    )


class AccountingEntryLine(Base):
    __tablename__ = "accounting_entry_lines"

    id           = Column(Integer, primary_key=True, index=True)
    source_id    = Column(Integer, unique=True, nullable=True, index=True)
    entry_id     = Column(Integer, ForeignKey("accounting_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    cuenta       = Column("account_code", String(20), nullable=True)
    nombre       = Column("account_name", String(200), nullable=True)
    debito       = Column("debit", Numeric(18, 2), nullable=False, default=0)
    credito      = Column("credit", Numeric(18, 2), nullable=False, default=0)
    tercero      = Column("partner_name", String(200), nullable=True)
    centro_costo = Column("cost_center", String(500), nullable=True)
    descripcion  = Column("name", Text, nullable=True)

    entry = relationship("AccountingEntry", back_populates="lines")
