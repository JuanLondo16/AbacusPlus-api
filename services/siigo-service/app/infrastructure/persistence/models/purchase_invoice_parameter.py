from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)

from app.infrastructure.config.database import Base


class PurchaseInvoiceParameter(Base):
    __tablename__ = "purchase_invoice_parameters"
    __table_args__ = (
        UniqueConstraint("provider", "account_key", "name", name="uq_purchase_invoice_param_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, index=True, default="siigo")
    account_key = Column(String(120), nullable=False, default="default")
    name = Column(String(120), nullable=False)
    document_id = Column(Integer, nullable=False)
    supplier_identification = Column(String(80), nullable=True)
    supplier_branch_office = Column(Integer, nullable=False, default=0)
    provider_invoice_prefix = Column(String(30), nullable=True)
    default_payment_id = Column(Integer, nullable=True)
    default_payment_due_date = Column(Date, nullable=True)
    default_item_type = Column(String(30), nullable=False, default="Account")
    default_item_code = Column(String(80), nullable=True)
    cost_center = Column(Integer, nullable=True)
    discount_type = Column(String(20), nullable=True)
    tax_included = Column(Boolean, nullable=True)
    supplier_by_item = Column(Boolean, nullable=True)
    currency_code = Column(String(3), nullable=True)
    currency_exchange_rate = Column(Numeric(18, 6), nullable=True)
    retentions = Column(JSON, nullable=False, default=list)
    taxes = Column(JSON, nullable=False, default=list)
    extra_payload = Column(JSON, nullable=False, default=dict)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
