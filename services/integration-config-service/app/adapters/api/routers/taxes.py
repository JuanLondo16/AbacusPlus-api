from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from openpyxl import Workbook

from app.adapters.api.routers._excel_template import style_header, xlsx_response
from app.application.dto.retention import SyncSiigoRetentionsResponse
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
| `nombre` | Si | `IVA 19%` | Nombre del impuesto. |
| `tipo` | Si | `IVA` | Tipo de impuesto. |
| `porcentaje` | Si | `19` | Porcentaje del impuesto (numero). |
| `activo` | No | `true` | Estado. Si se omite, queda `true`. |

`name`, `type`, `percentage` y `active` tambien se aceptan como alias: son el encabezado
en ingles con que este endpoint funciono antes de que la plantilla pasara a espanol.

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
    mode: str = Form(
        "upsert",
        description=(
            "`upsert`: actualiza impuestos existentes y agrega nuevos (no elimina). "
            "`replace`: elimina todo el catalogo de impuestos actual (incluidos los "
            "sincronizados desde SIIGO) antes de importar."
        ),
        examples=["upsert"],
    ),
    use_case: ImportTaxesUseCase = Depends(get_import_taxes_use_case),
) -> ImportTaxesResponse:
    content = await file.read()
    return use_case.execute(sheet_name=sheet_name, file_content=content, mode=mode)


@router.get(
    "/integrations/taxes/template",
    summary="Descargar plantilla Excel de impuestos",
    description=(
        "Genera un `.xlsx` listo para llenar y volver a importar via "
        "`POST /integrations/taxes/imports`.\n\n"
        "La hoja llega solo con encabezados: los impuestos son propios de cada empresa y no "
        "existe una tabla estandar que precargar.\n\n"
        f"{TAXES_EXCEL_STRUCTURE}"
    ),
    response_description="Archivo .xlsx de plantilla.",
)
def download_taxes_template():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Impuestos"
    sheet.append(["nombre", "tipo", "porcentaje", "activo"])
    style_header(
        sheet,
        notes={
            "nombre": "Nombre del impuesto, como aparecera en el selector.",
            "tipo": "Tipo de impuesto (IVA, Impoconsumo, etc).",
            "porcentaje": "Porcentaje del impuesto. Escriba 19 para un 19%.",
            "activo": "Opcional. true/false. Si se omite, queda true.",
        },
        widths={"A": 22, "B": 16, "C": 14, "D": 10},
    )
    return xlsx_response(workbook, "plantilla-impuestos.xlsx")


@router.post(
    "/integrations/taxes/siigo-syncs",
    dependencies=[Depends(require_write)],
    response_model=SyncSiigoRetentionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar impuestos y retenciones desde SIIGO",
    description=(
        "Consulta el endpoint `GET /v1/taxes` de la API de SIIGO y reparte cada fila: "
        "impuestos reales del documento (IVA, Impoconsumo, AdValorem) a la tabla local "
        "`integration_taxes`; retenciones (ReteIVA, Retefuente, Autorretención) a "
        "`integration_retentions`.\n\n"
        "**ReteICA se descarta**, con log explicito: SIIGO no conoce municipios, asi que su "
        "ReteICA sincronizada es un porcentaje plano sin poder verificarse contra ningun "
        "municipio real. El ReteICA solo se carga por Excel "
        "(`POST /integrations/retentions/imports`).\n\n"
        "La operacion es idempotente por `id` de SIIGO (con `name` como respaldo para filas "
        "heredadas). Si el token de acceso ha expirado o no existe, autentica automaticamente "
        "contra SIIGO y persiste el nuevo token antes de hacer la consulta.\n\n"
        "NOTA DE COMPATIBILIDAD: antes de esta separacion, este endpoint devolvia "
        "`{imported, taxes}` (solo impuestos, mezclados con retenciones). Ahora devuelve el "
        "resumen combinado; el campo `taxes` sigue existiendo con el mismo significado, y se "
        "agregan `retentions`, `retentions_imported`, `taxes_imported` y `reteica_ignored`."
    ),
    response_description="Resumen de impuestos y retenciones sincronizados.",
    responses={
        404: {"description": "No existe credencial activa para siigo con el account_key indicado."},
        502: {"description": "SIIGO no responde o retorna error."},
    },
)
def sync_taxes_from_siigo(
    use_case: SyncSiigoTaxesUseCase = Depends(get_sync_siigo_taxes_use_case),
) -> SyncSiigoRetentionsResponse:
    return use_case.execute()
