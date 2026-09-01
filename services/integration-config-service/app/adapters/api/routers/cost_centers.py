from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from openpyxl import Workbook

from app.adapters.api.routers._excel_template import style_header, xlsx_response
from app.application.dto.cost_center import (
    CostCenterResponse,
    ImportCostCentersResponse,
)
from app.application.use_cases.import_cost_centers import ImportCostCentersUseCase
from app.application.use_cases.sync_siigo_cost_centers import SyncSiigoCostCentersUseCase
from app.dependencies import (
    get_cost_center_repository,
    get_import_cost_centers_use_case,
    get_sync_siigo_cost_centers_use_case,
)
from app.infrastructure.config.auth_dependency import require_write
from app.infrastructure.persistence.repositories.cost_center_repository import CostCenterRepository

router = APIRouter()

COST_CENTERS_EXCEL_STRUCTURE = """
Estructura del Excel:

| Columna | Obligatoria | Ejemplo | Descripcion |
| --- | --- | --- | --- |
| `código` | Si | `1112` | Codigo del centro de costo. |
| `nombre` | Si | `Administracion` | Nombre del centro de costo. |
| `id_externo` | No | `13222` | ID externo del proveedor, si existe. |
| `activo` | No | `true` | Estado. Si se omite, queda `true`. |

Valores booleanos aceptados: `true`, `false`, `1`, `0`, `yes`, `no`, `si`, `sí`, `x`.

`code`, `name`, `external_id` y `active` tambien se aceptan como alias: son el
encabezado con que este endpoint funciono antes de que la plantilla pasara a espanol.
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
    return repository.list(active=active)


@router.post(
    "/integrations/cost-centers/imports",
    dependencies=[Depends(require_write)],
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
    mode: str = Form(
        "upsert",
        description=(
            "`upsert`: actualiza centros existentes y agrega nuevos (no elimina). "
            "`replace`: elimina todos los centros de costo actuales antes de importar."
        ),
        examples=["upsert"],
    ),
    use_case: ImportCostCentersUseCase = Depends(get_import_cost_centers_use_case),
) -> ImportCostCentersResponse:
    content = await file.read()
    return use_case.execute(
        sheet_name=sheet_name,
        file_content=content,
        mode=mode,
    )


@router.get(
    "/integrations/cost-centers/template",
    summary="Descargar plantilla Excel de centros de costo",
    description=(
        "Genera un `.xlsx` listo para llenar y volver a importar via "
        "`POST /integrations/cost-centers/imports`.\n\n"
        "La hoja llega solo con encabezados: los centros de costo son propios de cada "
        "empresa y no existe una tabla estandar que precargar.\n\n"
        f"{COST_CENTERS_EXCEL_STRUCTURE}"
    ),
    response_description="Archivo .xlsx de plantilla.",
)
def download_cost_centers_template():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Centros de costo"
    sheet.append(["código", "nombre", "id_externo", "activo"])
    style_header(
        sheet,
        notes={
            "código": "Codigo del centro de costo. Identifica cada fila al importar de nuevo.",
            "nombre": "Nombre del centro de costo.",
            "id_externo": "Opcional. ID externo en el proveedor, si existe.",
            "activo": "Opcional. true/false. Si se omite, queda true.",
        },
        widths={"A": 14, "B": 28, "C": 16, "D": 10},
    )
    return xlsx_response(workbook, "plantilla-centros-costo.xlsx")


@router.post(
    "/integrations/cost-centers/siigo-syncs",
    dependencies=[Depends(require_write)],
    response_model=ImportCostCentersResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar centros de costo desde SIIGO",
    description=(
        "Consulta el endpoint `GET /v1/cost-centers` de la API de SIIGO y sincroniza "
        "los resultados en la tabla local `integration_cost_centers`.\n\n"
        "La operacion es idempotente por `code`: actualiza si ya existe, crea si no. "
        "Los centros de costo que ya no existen en SIIGO son eliminados de la tabla local.\n\n"
        "Si el token de acceso ha expirado o no existe, autentica automaticamente contra SIIGO "
        "y persiste el nuevo token antes de hacer la consulta."
    ),
    response_description="Resumen de centros de costo sincronizados y listado resultante.",
    responses={
        404: {"description": "No existe credencial activa para siigo con el account_key indicado."},
        502: {"description": "SIIGO no responde o retorna error."},
    },
)
def sync_cost_centers_from_siigo(
    use_case: SyncSiigoCostCentersUseCase = Depends(get_sync_siigo_cost_centers_use_case),
) -> ImportCostCentersResponse:
    return use_case.execute()
