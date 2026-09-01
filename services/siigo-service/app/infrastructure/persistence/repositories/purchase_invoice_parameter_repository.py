from typing import Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.purchase_invoice_parameter import (
    PurchaseInvoiceParameter,
)


class PurchaseInvoiceParameterRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: dict) -> PurchaseInvoiceParameter:
        model = PurchaseInvoiceParameter(**data)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def list(
        self, provider: str, account_key: Optional[str] = None
    ) -> list[PurchaseInvoiceParameter]:
        """Plantillas del proveedor. Sin `account_key` devuelve las de todas las cuentas.

        Que el filtro sea opcional importa para RF-05: la contabilización necesita «la
        plantilla vigente», y el `account_key` real lo define cada cliente al registrar su
        credencial ('Ikbo', 'empresa-principal', …). Exigir un valor obligaba a quien llama a
        adivinarlo, y adivinar «default» hacía invisible cualquier plantilla registrada con
        otra clave.
        """
        consulta = self.db.query(PurchaseInvoiceParameter).filter(
            PurchaseInvoiceParameter.provider == provider
        )
        if account_key is not None:
            consulta = consulta.filter(PurchaseInvoiceParameter.account_key == account_key)
        return consulta.order_by(PurchaseInvoiceParameter.name.asc()).all()
