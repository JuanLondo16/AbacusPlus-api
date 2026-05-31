from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.application.dto.cost_center import CostCenterResponse, ImportCostCentersResponse
from app.application.use_cases.import_cost_centers import (
    _DEFAULT_ACCOUNT_KEY,
    _DEFAULT_PROVIDER,
    ImportCostCentersUseCase,
)
from app.dependencies import get_cost_center_repository, get_import_cost_centers_use_case
from app.infrastructure.persistence.repositories.cost_center_repository import CostCenterRepository

router = APIRouter()

COST_CENTERS_EXCEL_STRUCTURE = """
Estructura del Excel:

| Columna | Obligatoria | Ejemplo | Descripcion |
| --- | --- | --- | --- |
| `code` | Si | `1112` | Codigo del centro de costo. |
| `name` | Si | `Administracion` | Nombre del centro de costo. |
| `external_id` | No | `13222` | ID externo del proveedor, si existe. |
| `active` | No | `true` | Estado. Si se omite, queda `true`. |

Valores booleanos aceptados: `true`, `false`, `1`, `0`, `yes`, `no`, `si`, `sí`, `x`.
"""


@router.get(
    "/integrations/cost-centers",
    response_model=list[CostCenterResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar centros de costo",
    description=(
        "Retorna todos los centros de costo registrados en la tabla local `integration_cost_centers`.\n\n"
        "Usa el filtro `active` para obtener solo los activos o solo los inactivos."
    ),
    response_description="Lista de centros de costo ordenados por codigo.",
    responses={},
)
def list_cost_centers(
    active: Optional[bool] = Query(
        None, description="Filtrar por estado activo. Si se omite, retorna todos."
    ),
    repository: CostCenterRepository = Depends(get_cost_center_repository),
) -> list[CostCenterResponse]:
    return repository.list(
        provider=_DEFAULT_PROVIDER, account_key=_DEFAULT_ACCOUNT_KEY, active=active
    )


@router.post(
    "/integrations/cost-centers/imports",
    response_model=ImportCostCentersResponse,
    status_code=status.HTTP_200_OK,
    summary="Importar centros de costo desde Excel",
    description=(
        "Recibe un archivo `.xlsx` con centros de costo y alimenta "
        "la tabla local `integration_cost_centers`.\n\n"
        "La operacion es idempotente por `code`: si el centro ya existe, "
        "actualiza sus datos; si no existe, lo crea.\n\n"
        f"{COST_CENTERS_EXCEL_STRUCTURE}"
    ),
    response_description="Resumen de centros importados y listado resultante.",
    responses={
        400: {"description": "Archivo invalido, columnas faltantes o filas con datos incorrectos."},
    },
)
async def import_cost_centers_from_excel(
    sheet_name: Optional[str] = Form(
        None, description="Nombre de hoja a leer. Si se omite, usa la primera hoja."
    ),
    file: UploadFile = File(..., description="Archivo Excel .xlsx con los centros de costo."),
    use_case: ImportCostCentersUseCase = Depends(get_import_cost_centers_use_case),
) -> ImportCostCentersResponse:
    content = await file.read()
    return use_case.execute(
        sheet_name=sheet_name,
        file_content=content,
    )
