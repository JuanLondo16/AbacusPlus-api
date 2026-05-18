from typing import List

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

    def list(self, provider: str, account_key: str) -> List[PurchaseInvoiceParameter]:
        return (
            self.db.query(PurchaseInvoiceParameter)
            .filter(
                PurchaseInvoiceParameter.provider == provider,
                PurchaseInvoiceParameter.account_key == account_key,
            )
            .order_by(PurchaseInvoiceParameter.name.asc())
            .all()
        )
