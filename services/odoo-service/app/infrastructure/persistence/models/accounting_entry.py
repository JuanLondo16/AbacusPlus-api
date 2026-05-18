from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.infrastructure.config.database import Base


class AccountingEntry(Base):
    __tablename__ = "accounting_entries"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, unique=True, nullable=True, index=True)
    source = Column(String(10), nullable=True, default="odoo")
    document_id = Column(Integer, nullable=True, index=True)  # ref a documents.id, sin FK cross-service
    name = Column(String(100), nullable=True)
    date = Column(Date, nullable=True, index=True)
    ref = Column(String(200), nullable=True)
    move_type = Column(String(20), nullable=True, index=True)
    state = Column(String(20), nullable=True, index=True)
    journal_id = Column(Integer, nullable=True)
    journal_name = Column(String(100), nullable=True)
    partner_id = Column(Integer, nullable=True, index=True)
    partner_name = Column(String(200), nullable=True)
    partner_vat = Column(String(50), nullable=True)
    currency_name = Column(String(10), nullable=True)
    amount_untaxed = Column(Numeric(18, 2), nullable=False, default=0)
    amount_tax = Column(Numeric(18, 2), nullable=False, default=0)
    amount_total = Column(Numeric(18, 2), nullable=False, default=0)
    narration = Column(Text, nullable=True)
    batch_id = Column(String(36), nullable=True, index=True)
    extracted_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    lines = relationship(
        "AccountingEntryLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="AccountingEntryLine.sequence",
    )


class AccountingEntryLine(Base):
    __tablename__ = "accounting_entry_lines"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, unique=True, nullable=True, index=True)
    entry_id = Column(Integer, ForeignKey("accounting_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    source_move_id = Column(Integer, nullable=True)
    sequence = Column(Integer, nullable=False, default=0)
    account_code = Column(String(20), nullable=True)
    account_name = Column(String(200), nullable=True)
    partner_name = Column(String(200), nullable=True)
    name = Column(String(500), nullable=True)
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)
    amount_currency = Column(Numeric(18, 2), nullable=False, default=0)
    cost_center = Column(String(500), nullable=True)
    date_maturity = Column(Date, nullable=True)
    extracted_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    entry = relationship("AccountingEntry", back_populates="lines")
