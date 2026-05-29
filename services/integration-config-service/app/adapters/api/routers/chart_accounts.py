from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.application.dto.chart_account import ImportChartAccountsResponse
from app.application.use_cases.import_chart_accounts import ImportChartAccountsUseCase
from app.dependencies import get_import_chart_accounts_use_case

router = APIRouter()

CHART_ACCOUNTS_EXCEL_STRUCTURE = """
Estructura del Excel:

| Columna | Obligatoria | Ejemplo | Descripcion |
| --- | --- | --- | --- |
| `code` | Si | `510505` | Codigo contable. |
| `name` | Si | `Gastos de personal` | Nombre de la cuenta. |
| `external_id` | No | `12345` | ID externo del proveedor, si existe. |
| `account_type` | No | `Expense` | Tipo o clase de cuenta. |
| `level` | No | `4` | Nivel jerarquico. |
| `parent_code` | No | `5105` | Codigo de cuenta padre. |
| `accepts_movements` | No | `true` | Si permite movimientos contables. |
| `active` | No | `true` | Estado. Si se omite, queda `true`. |

Valores booleanos aceptados: `true`, `false`, `1`, `0`, `yes`, `no`, `si`, `sí`, `x`.
"""


@router.post(
    "/integrations/chart-accounts/imports",
    response_model=ImportChartAccountsResponse,
    status_code=status.HTTP_200_OK,
    summary="Importar plan de cuentas desde Excel",
    description=(
        "Recibe un archivo `.xlsx` con el plan de cuentas de un proveedor y alimenta "
        "la tabla local `integration_chart_accounts`.\n\n"
        "La operacion es idempotente por `provider`, `account_key` y `code`: si la cuenta "
        "ya existe, actualiza sus datos; si no existe, la crea. Use este endpoint para "
        "cargar planes de cuentas manuales de SIIGO u otras aplicaciones sin depender "
        "de un API externo.\n\n"
        f"{CHART_ACCOUNTS_EXCEL_STRUCTURE}"
    ),
    response_description="Resumen de cuentas importadas y listado resultante.",
    responses={
        400: {"description": "Archivo invalido, columnas faltantes o filas con datos incorrectos."},
    },
)
async def import_chart_accounts_from_excel(
    provider: str = Form(..., description="Proveedor al que pertenece el plan.", examples=["siigo"]),
    account_key: str = Form("default", description="Empresa/cuenta conectada.", examples=["empresa-principal"]),
    sheet_name: Optional[str] = Form(None, description="Nombre de hoja a leer. Si se omite, usa la primera hoja."),
    file: UploadFile = File(..., description="Archivo Excel .xlsx con el plan de cuentas."),
    use_case: ImportChartAccountsUseCase = Depends(get_import_chart_accounts_use_case),
) -> ImportChartAccountsResponse:
    content = await file.read()
    return use_case.execute(
        provider=provider,
        account_key=account_key,
        sheet_name=sheet_name,
        file_content=content,
    )
