from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.application.dto.tax import ImportTaxesResponse, TaxResponse
from app.application.use_cases.import_taxes import ImportTaxesUseCase
from app.application.use_cases.sync_siigo_taxes import SyncSiigoTaxesUseCase
from app.dependencies import (
    get_import_taxes_use_case,
    get_sync_siigo_taxes_use_case,
    get_tax_repository,
)
from app.infrastructure.config.auth_dependency import require_write
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository

router = APIRouter()

TAXES_EXCEL_STRUCTURE = """
Estructura del Excel:

| Columna | Obligatoria | Ejemplo | Descripcion |
| --- | --- | --- | --- |
| `name` | Si | `IVA 19%` | Nombre del impuesto. |
| `type` | Si | `IVA` | Tipo de impuesto. |
| `percentage` | Si | `19` | Porcentaje del impuesto (numero). |
| `active` | No | `true` | Estado. Si se omite, queda `true`. |

Valores booleanos aceptados: `true`, `false`, `1`, `0`, `yes`, `no`, `si`, `sí`, `x`.
"""


@router.get(
    "/integrations/taxes",
    response_model=list[TaxResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar impuestos",
    description=(
        "Retorna todos los impuestos registrados en la tabla local `integration_taxes`.\n\n"
        "Usa el filtro `active` para obtener solo los activos o solo los inactivos."
    ),
    response_description="Lista de impuestos ordenados por nombre.",
    responses={},
)
def list_taxes(
    active: Optional[bool] = Query(
        None, description="Filtrar por estado activo. Si se omite, retorna todos."
    ),
    repository: TaxRepository = Depends(get_tax_repository),
) -> list[TaxResponse]:
    return repository.list(active=active)


@router.post(
    "/integrations/taxes/imports",
    dependencies=[Depends(require_write)],
    response_model=ImportTaxesResponse,
    status_code=status.HTTP_200_OK,
    summary="Importar impuestos desde Excel",
    description=(
        "Recibe un archivo `.xlsx` con impuestos y alimenta "
        "la tabla local `integration_taxes`.\n\n"
        "La operacion es idempotente por `name`: si el impuesto ya existe, "
        "actualiza sus datos; si no existe, lo crea.\n\n"
        f"{TAXES_EXCEL_STRUCTURE}"
    ),
    response_description="Resumen de impuestos importados y listado resultante.",
    responses={
        400: {"description": "Archivo invalido, columnas faltantes o filas con datos incorrectos."},
    },
)
async def import_taxes_from_excel(
    sheet_name: Optional[str] = Form(
        None, description="Nombre de hoja a leer. Si se omite, usa la primera hoja."
    ),
    file: UploadFile = File(..., description="Archivo Excel .xlsx con los impuestos."),
    use_case: ImportTaxesUseCase = Depends(get_import_taxes_use_case),
) -> ImportTaxesResponse:
    content = await file.read()
    return use_case.execute(sheet_name=sheet_name, file_content=content)


@router.post(
    "/integrations/taxes/siigo-syncs",
    dependencies=[Depends(require_write)],
    response_model=ImportTaxesResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar impuestos desde SIIGO",
    description=(
        "Consulta el endpoint `GET /v1/taxes` de la API de SIIGO y sincroniza "
        "los resultados en la tabla local `integration_taxes`.\n\n"
        "La operacion es idempotente por `name`: actualiza si ya existe, crea si no.\n\n"
        "Si el token de acceso ha expirado o no existe, autentica automaticamente contra SIIGO "
        "y persiste el nuevo token antes de hacer la consulta."
    ),
    response_description="Resumen de impuestos sincronizados y listado resultante.",
    responses={
        404: {"description": "No existe credencial activa para siigo con el account_key indicado."},
        502: {"description": "SIIGO no responde o retorna error."},
    },
)
def sync_taxes_from_siigo(
    use_case: SyncSiigoTaxesUseCase = Depends(get_sync_siigo_taxes_use_case),
) -> ImportTaxesResponse:
    return use_case.execute()
