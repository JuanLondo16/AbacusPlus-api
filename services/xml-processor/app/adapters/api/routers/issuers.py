from fastapi import APIRouter, Depends, HTTPException, status

from app.application.dto.issuer import IssuerResponse
from app.application.use_cases.query_issuers import GetIssuerByNitUseCase
from app.dependencies import get_issuer_by_nit_use_case

router = APIRouter()


@router.get(
    "/issuers/{nit}",
    response_model=IssuerResponse,
    summary="Obtener emisor por NIT",
    description=(
        "Retorna los datos de un emisor registrado en el sistema, incluyendo su cuenta contable "
        "de cuentas por pagar (`account_number`) y su régimen tributario (`tipo_contribuyente`).\n\n"
        "Estos campos son utilizados por el llm-service para enriquecer el contexto de causación "
        "contable: la cuenta CxP del proveedor y si aplica IVA descontable."
    ),
    response_description="Datos del emisor con cuenta CxP y régimen.",
    responses={
        404: {"description": "Emisor no encontrado."},
    },
)
def get_issuer_by_nit(
    nit: str,
    use_case: GetIssuerByNitUseCase = Depends(get_issuer_by_nit_use_case),
):
    issuer = use_case.execute(nit)
    if issuer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emisor con NIT {nit} no encontrado.",
        )
    return issuer
