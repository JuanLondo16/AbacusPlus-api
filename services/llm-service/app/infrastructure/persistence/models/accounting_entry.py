from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.infrastructure.config.database import Base


class AccountingEntry(Base):
    __tablename__ = "accounting_entries"

    id               = Column(Integer, primary_key=True, index=True)
    document_id      = Column(Integer, nullable=False, index=True)
    system_prompt_id = Column(Integer, nullable=True)
    model_used       = Column(String(50), nullable=True)
    status           = Column(String(20), nullable=False)   # generated | error
    error_message    = Column(Text, nullable=True)
    # Contexto RAG utilizado: lista de chunks con source_type, similarity y content.
    # Solo se usa para inferir la distribución contable (cuentas PUC), no los valores.
    rag_context      = Column(JSON, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    lines = relationship(
        "AccountingEntryLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="AccountingEntryLine.id",
    )


class AccountingEntryLine(Base):
    __tablename__ = "accounting_entry_lines"

    id           = Column(Integer, primary_key=True, index=True)
    entry_id     = Column(Integer, ForeignKey("accounting_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    cuenta       = Column(String(20), nullable=False, index=True)
    nombre       = Column(String(200), nullable=False)
    debito       = Column(Numeric(18, 2), nullable=False, default=0)
    credito      = Column(Numeric(18, 2), nullable=False, default=0)
    tercero      = Column(String(100), nullable=True)
    centro_costo = Column(String(200), nullable=True)
    descripcion  = Column(Text, nullable=True)

    entry = relationship("AccountingEntry", back_populates="lines")
