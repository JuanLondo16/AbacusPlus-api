from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PurchaseInvoiceParameterCreate(BaseModel):
    provider: str = Field("siigo", description="Proveedor objetivo.", examples=["siigo"])
    account_key: str = Field("default", description="Cuenta/empresa conectada.", examples=["empresa-principal"])
    name: str = Field(..., description="Nombre interno de la plantilla.", examples=["compra-default"])
    document_id: int = Field(..., description="ID del tipo de comprobante SIIGO. Consultar /document-types?type=FC.", examples=[58246])
    supplier_identification: Optional[str] = Field(None, description="Identificacion del proveedor por defecto.", examples=["101020201"])
    supplier_branch_office: int = Field(0, description="Sucursal del proveedor.", examples=[0])
    provider_invoice_prefix: Optional[str] = Field(None, description="Prefijo de factura del proveedor.", examples=["VEN"])
    default_payment_id: Optional[int] = Field(None, description="ID del medio de pago. Consultar /payment-types con filtro FC.", examples=[51279])
    default_payment_due_date: Optional[date] = Field(None, description="Fecha de vencimiento por defecto si el pago la requiere.")
    default_item_type: str = Field("Account", description="Tipo de item SIIGO: Product, FixedAsset o Account.", examples=["Account"])
    default_item_code: Optional[str] = Field(None, description="Codigo del producto, activo fijo o cuenta.", examples=["510505"])
    cost_center: Optional[int] = Field(None, description="ID de centro de costo SIIGO.", examples=[235])
    discount_type: Optional[str] = Field(None, description="Tipo de descuento: Percentage o Value.", examples=["Value"])
    tax_included: Optional[bool] = Field(None, description="Indica si el precio incluye impuestos.", examples=[False])
    supplier_by_item: Optional[bool] = Field(None, description="Permite enviar proveedor por item.", examples=[False])
    currency_code: Optional[str] = Field(None, description="Codigo de moneda extranjera si aplica.", examples=["USD"])
    currency_exchange_rate: Optional[Decimal] = Field(None, description="Tasa de cambio si aplica.", examples=[3825.03])
    retentions: List[Dict[str, Any]] = Field(default_factory=list, description="Retenciones por defecto, con IDs de /taxes.")
    taxes: List[Dict[str, Any]] = Field(default_factory=list, description="Impuestos por defecto para items, con IDs de /taxes.")
    extra_payload: Dict[str, Any] = Field(default_factory=dict, description="Parametros adicionales para futuras extensiones SIIGO.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "provider": "siigo",
                "account_key": "empresa-principal",
                "name": "compra-default",
                "document_id": 58246,
                "supplier_identification": "101020201",
                "supplier_branch_office": 0,
                "provider_invoice_prefix": "VEN",
                "default_payment_id": 51279,
                "default_item_type": "Account",
                "default_item_code": "510505",
                "tax_included": False,
                "retentions": [],
                "taxes": [{"id": 13156}],
            }
        }
    }


class PurchaseInvoiceParameterResponse(PurchaseInvoiceParameterCreate):
    id: int = Field(..., description="ID local de la plantilla.", examples=[1])
    active: bool = Field(..., description="Estado de la plantilla.", examples=[True])

    model_config = {"from_attributes": True}
