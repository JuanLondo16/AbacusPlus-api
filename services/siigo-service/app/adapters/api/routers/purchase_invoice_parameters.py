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
    "/siigo/purchase-invoice-parameters",
    response_model=PurchaseInvoiceParameterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear parametros para facturas de compra SIIGO",
    description=(
        "Guarda una plantilla local con los parametros que SIIGO requiere para crear "
        "facturas de compra mediante `POST /v1/purchases`.\n\n"
        "Incluye `document.id`, proveedor, factura del proveedor, item por defecto, "
        "impuestos, retenciones, centro de costo, moneda y medio de pago. "
        "Estos datos quedan en PostgreSQL para reutilizarse cuando se implemente "
        "la creacion automatica de facturas de compra."
    ),
    response_description="Plantilla creada para facturas de compra.",
    responses={400: {"description": "Tipo de item o descuento no soportado por SIIGO."}},
)
def create_purchase_invoice_parameters(
    request: PurchaseInvoiceParameterCreate,
    use_case: ManagePurchaseInvoiceParametersUseCase = Depends(
        get_purchase_invoice_parameters_use_case
    ),
) -> PurchaseInvoiceParameterResponse:
    return use_case.create(request)


@router.get(
    "/siigo/purchase-invoice-parameters",
    response_model=list[PurchaseInvoiceParameterResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar parametros de facturas de compra SIIGO",
    description=(
        "Lista las plantillas locales usadas para construir payloads de facturas de compra "
        "hacia SIIGO. No llama al API externo."
    ),
    response_description="Listado de plantillas de parametros.",
)
def list_purchase_invoice_parameters(
    account_key: str = "default",
    use_case: ManagePurchaseInvoiceParametersUseCase = Depends(
        get_purchase_invoice_parameters_use_case
    ),
) -> list[PurchaseInvoiceParameterResponse]:
    return use_case.list(account_key=account_key)
