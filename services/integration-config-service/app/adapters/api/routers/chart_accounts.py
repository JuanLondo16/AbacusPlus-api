from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.application.dto.chart_account import ChartAccountResponse, ImportChartAccountsResponse
from app.application.use_cases.import_chart_accounts import ImportChartAccountsUseCase
from app.dependencies import get_import_chart_accounts_use_case
from app.infrastructure.config.auth_dependency import get_tenant_db, require_write
from app.infrastructure.persistence.repositories.chart_account_repository import (
    ChartAccountRepository,
)

router = APIRouter()

CHART_ACCOUNTS_EXCEL_STRUCTURE = """
Estructura del Excel:

| Columna | Obligatoria | Ejemplo | Descripcion |
| --- | --- | --- | --- |
| `code` | Si | `510505` | Codigo contable. |
| `name` | Si | `Gastos de personal` | Nombre de la cuenta. |
| `external_id` | No | `12345` | ID externo en el sistema de origen, si existe. |
| `account_type` | No | `Expense` | Tipo o clase de cuenta. |
| `level` | No | `4` | Nivel jerarquico. Si se omite, se infiere de la longitud del codigo. |
| `parent_code` | No | `5105` | Codigo de cuenta padre. |
| `accepts_movements` | No | `true` | Si permite movimientos contables. |
| `active` | No | `true` | Estado. Si se omite, queda `true`. |

Valores booleanos aceptados: `true`, `false`, `1`, `0`, `yes`, `no`, `si`, `sí`, `x`.

Se aceptan tambien los encabezados en espanol de la exportacion de SIIGO, que se
mapean a las columnas canonicas: `Codigo`/`Codigo` -> `code`, `Nombre` -> `name`,
`Tipo de cuenta` -> `account_type`, `Nivel` -> `level`, `Cuenta padre` -> `parent_code`,
`Activo` -> `active`. Un encabezado canonico explicito siempre tiene prioridad sobre
su alias. Las columnas no reconocidas (p. ej. `Categoria`, `Nivel agrupacion`) se
conservan en `raw_payload` pero no se interpretan.

`accepts_movements` se recalcula tras la importacion: una cuenta acepta movimientos
solo si es hoja del arbol importado (ninguna otra cuenta del archivo la tiene como
prefijo).
"""


@router.get(
    "/integrations/chart-accounts",
    response_model=list[ChartAccountResponse],
    status_code=200,
    summary="Listar plan de cuentas",
    description=(
        "Retorna el plan de cuentas almacenado localmente para la cuenta indicada.\n\n"
        "No realiza llamadas externas. Devuelve los datos importados via "
        "`POST /api/v1/integrations/chart-accounts/imports` o sincronizados "
        "desde el proveedor contable configurado."
    ),
    response_description="Listado de cuentas contables almacenadas.",
)
def list_chart_accounts(
    active: Optional[bool] = None,
    db=Depends(get_tenant_db),
) -> list[ChartAccountResponse]:
    return ChartAccountRepository(db).list(active=active)


@router.post(
    "/integrations/chart-accounts/imports",
    dependencies=[Depends(require_write)],
    response_model=ImportChartAccountsResponse,
    status_code=status.HTTP_200_OK,
    summary="Importar plan de cuentas desde Excel",
    description=(
        "Recibe un archivo `.xlsx` con el plan de cuentas y alimenta "
        "la tabla local `integration_chart_accounts`.\n\n"
        "La operacion es idempotente por `account_key` y `code`: si la cuenta "
        "ya existe, actualiza sus datos; si no existe, la crea.\n\n"
        f"{CHART_ACCOUNTS_EXCEL_STRUCTURE}"
    ),
    response_description="Resumen de cuentas importadas y listado resultante.",
    responses={
        400: {"description": "Archivo invalido, columnas faltantes o filas con datos incorrectos."},
    },
)
async def import_chart_accounts_from_excel(
    file: UploadFile = File(..., description="Archivo Excel .xlsx con el plan de cuentas."),
    mode: str = Form(
        "upsert",
        description=(
            "`upsert`: actualiza cuentas existentes y agrega nuevas (no elimina). "
            "`replace`: elimina todo el plan actual antes de importar."
        ),
        examples=["upsert"],
    ),
    sheet_name: Optional[str] = Form(
        None, description="Nombre de hoja a leer. Si se omite, usa la primera hoja."
    ),
    use_case: ImportChartAccountsUseCase = Depends(get_import_chart_accounts_use_case),
) -> ImportChartAccountsResponse:
    content = await file.read()
    return use_case.execute(
        file_content=content,
        sheet_name=sheet_name,
        mode=mode,
    )
