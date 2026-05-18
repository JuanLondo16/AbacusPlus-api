from typing import List, Optional

from fastapi import APIRouter, Depends, status

from app.application.dto.purchase_invoice_parameter import (
    PurchaseInvoiceParameterCreate,
    PurchaseInvoiceParameterResponse,
)
from app.application.use_cases.manage_purchase_invoice_parameters import (
    ManagePurchaseInvoiceParametersUseCase,
)
from app.dependencies import get_purchase_invoice_parameters_use_case

router = APIRouter()


@router.post(
    "/integrations/purchase-invoice-parameters",
    response_model=PurchaseInvoiceParameterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear parametros para facturas de compra",
    description=(
        "Guarda una plantilla local con parametros reutilizables para construir facturas "
        "de compra en proveedores externos.\n\n"
        "El campo `provider` permite que la misma tabla soporte SIIGO, Odoo u otras "
        "aplicaciones. Los campos comunes quedan normalizados y los detalles propios "
        "de cada proveedor pueden ir en `extra_payload`."
    ),
    response_description="Plantilla creada para facturas de compra.",
    responses={400: {"description": "Tipo de item o descuento no soportado."}},
)
def create_purchase_invoice_parameters(
    request: PurchaseInvoiceParameterCreate,
    use_case: ManagePurchaseInvoiceParametersUseCase = Depends(get_purchase_invoice_parameters_use_case),
) -> PurchaseInvoiceParameterResponse:
    return use_case.create(request)


@router.get(
    "/integrations/purchase-invoice-parameters",
    response_model=List[PurchaseInvoiceParameterResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar parametros de facturas de compra",
    description=(
        "Lista las plantillas locales usadas por los adaptadores de integracion para "
        "crear facturas de compra. Puede filtrarse por `provider` y `account_key`."
    ),
    response_description="Listado de plantillas de parametros.",
)
def list_purchase_invoice_parameters(
    provider: Optional[str] = None,
    account_key: Optional[str] = None,
    use_case: ManagePurchaseInvoiceParametersUseCase = Depends(get_purchase_invoice_parameters_use_case),
) -> List[PurchaseInvoiceParameterResponse]:
    return use_case.list(provider=provider, account_key=account_key)
