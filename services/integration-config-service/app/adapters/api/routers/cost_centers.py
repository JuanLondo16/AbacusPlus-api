from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.application.dto.cost_center import ImportCostCentersResponse
from app.application.use_cases.import_cost_centers import ImportCostCentersUseCase
from app.dependencies import get_import_cost_centers_use_case

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


@router.post(
    "/integrations/cost-centers/imports",
    response_model=ImportCostCentersResponse,
    status_code=status.HTTP_200_OK,
    summary="Importar centros de costo desde Excel",
    description=(
        "Recibe un archivo `.xlsx` con centros de costo de un proveedor y alimenta "
        "la tabla local `integration_cost_centers`.\n\n"
        "La operacion es idempotente por `provider`, `account_key` y `code`: si el "
        "centro ya existe, actualiza sus datos; si no existe, lo crea.\n\n"
        f"{COST_CENTERS_EXCEL_STRUCTURE}"
    ),
    response_description="Resumen de centros importados y listado resultante.",
    responses={
        400: {"description": "Archivo invalido, columnas faltantes o filas con datos incorrectos."},
    },
)
async def import_cost_centers_from_excel(
    provider: str = Form(..., description="Proveedor al que pertenecen los centros.", examples=["siigo"]),
    account_key: str = Form("default", description="Empresa/cuenta conectada.", examples=["empresa-principal"]),
    sheet_name: Optional[str] = Form(None, description="Nombre de hoja a leer. Si se omite, usa la primera hoja."),
    file: UploadFile = File(..., description="Archivo Excel .xlsx con los centros de costo."),
    use_case: ImportCostCentersUseCase = Depends(get_import_cost_centers_use_case),
) -> ImportCostCentersResponse:
    content = await file.read()
    return use_case.execute(
        provider=provider,
        account_key=account_key,
        sheet_name=sheet_name,
        file_content=content,
    )
