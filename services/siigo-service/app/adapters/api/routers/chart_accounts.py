from fastapi import APIRouter, Depends, status

from app.application.dto.chart_account import (
    SyncChartAccountsRequest,
    SyncChartAccountsResponse,
)
from app.application.use_cases.sync_chart_accounts import SyncChartAccountsUseCase
from app.dependencies import get_sync_chart_accounts_use_case

router = APIRouter()


@router.post(
    "/siigo/chart-accounts/syncs",
    response_model=SyncChartAccountsResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar plan de cuentas desde SIIGO",
    description=(
        "Consulta el recurso de plan de cuentas de SIIGO configurado para la cuenta, "
        "normaliza los campos principales y alimenta la tabla local "
        "`integration_chart_accounts`.\n\n"
        "La documentacion publica de SIIGO confirma el esquema de autenticacion y el uso "
        "de recursos REST bajo `/v1`; como el endpoint de plan de cuentas puede depender "
        "de habilitacion/cuenta, la ruta se puede enviar en el body o guardar en "
        "`chart_accounts_path` al registrar credenciales."
    ),
    response_description="Cantidad sincronizada y listado local resultante.",
    responses={
        400: {"description": "Ruta SIIGO invalida o payload de cuenta incompleto."},
        404: {"description": "No existe credencial activa de SIIGO."},
        502: {"description": "Error consultando SIIGO."},
    },
)
def sync_chart_accounts(
    request: SyncChartAccountsRequest,
    use_case: SyncChartAccountsUseCase = Depends(get_sync_chart_accounts_use_case),
) -> SyncChartAccountsResponse:
    return use_case.execute(request)
