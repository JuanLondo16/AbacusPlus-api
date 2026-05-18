from typing import List, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.purchase_invoice_parameter import PurchaseInvoiceParameter


class PurchaseInvoiceParameterRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: dict) -> PurchaseInvoiceParameter:
        model = PurchaseInvoiceParameter(**data)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def list(self, provider: Optional[str] = None, account_key: Optional[str] = None) -> List[PurchaseInvoiceParameter]:
        query = self.db.query(PurchaseInvoiceParameter)
        if provider:
            query = query.filter(PurchaseInvoiceParameter.provider == provider)
        if account_key:
            query = query.filter(PurchaseInvoiceParameter.account_key == account_key)
        return query.order_by(
            PurchaseInvoiceParameter.provider.asc(),
            PurchaseInvoiceParameter.account_key.asc(),
            PurchaseInvoiceParameter.name.asc(),
        ).all()
