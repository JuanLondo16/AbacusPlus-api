from typing import List, Optional

from fastapi import APIRouter, Depends, status

from app.application.dto.chart_account import (
    ChartAccountResponse,
    SyncChartAccountsRequest,
    SyncChartAccountsResponse,
)
from app.application.use_cases.sync_chart_accounts import SyncChartAccountsUseCase
from app.dependencies import get_sync_chart_accounts_use_case
from app.infrastructure.config.database import get_db
from app.infrastructure.persistence.repositories.chart_account_repository import ChartAccountRepository

router = APIRouter()


@router.post(
    "/siigo/chart-accounts/sync",
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


@router.get(
    "/siigo/chart-accounts",
    response_model=List[ChartAccountResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar cuentas contables almacenadas",
    description=(
        "Retorna el plan de cuentas previamente sincronizado desde SIIGO. "
        "No realiza llamadas externas; consulta unicamente PostgreSQL."
    ),
    response_description="Listado local de cuentas contables.",
)
def list_chart_accounts(
    account_key: str = "default",
    active: Optional[bool] = None,
    db=Depends(get_db),
) -> List[ChartAccountResponse]:
    return ChartAccountRepository(db).list("siigo", account_key, active=active)
