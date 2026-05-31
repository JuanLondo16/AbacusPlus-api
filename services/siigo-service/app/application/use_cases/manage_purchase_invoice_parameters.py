from app.application.dto.purchase_invoice_parameter import PurchaseInvoiceParameterCreate
from app.domain.exceptions.base import ValidationException
from app.infrastructure.persistence.repositories.purchase_invoice_parameter_repository import (
    PurchaseInvoiceParameterRepository,
)


class ManagePurchaseInvoiceParametersUseCase:
    VALID_ITEM_TYPES = {"Product", "FixedAsset", "Account"}
    VALID_DISCOUNT_TYPES = {"Percentage", "Value"}

    def __init__(self, repository: PurchaseInvoiceParameterRepository):
        self.repository = repository

    def create(self, request: PurchaseInvoiceParameterCreate):
        if request.provider.lower() != "siigo":
            raise ValidationException(
                "Only SIIGO purchase invoice parameters are supported for now"
            )
        if request.default_item_type not in self.VALID_ITEM_TYPES:
            raise ValidationException("default_item_type must be Product, FixedAsset or Account")
        if request.discount_type and request.discount_type not in self.VALID_DISCOUNT_TYPES:
            raise ValidationException("discount_type must be Percentage or Value")

        data = request.model_dump()
        data["provider"] = data["provider"].lower()
        return self.repository.create(data)

    def list(self, account_key: str = "default"):
        return self.repository.list("siigo", account_key)
