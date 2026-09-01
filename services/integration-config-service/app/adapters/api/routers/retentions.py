from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.application.dto.retention import (
    ImportRetentionsResponse,
    RetentionResponse,
    SyncSiigoRetentionsResponse,
)
from app.application.use_cases.import_retentions import ImportRetentionsUseCase
from app.application.use_cases.sync_siigo_taxes import SyncSiigoTaxesUseCase
from app.dependencies import (
    get_import_retentions_use_case,
    get_retention_repository,
    get_sync_siigo_taxes_use_case,
)
from app.infrastructure.config.auth_dependency import require_write
from app.infrastructure.persistence.repositories.retention_repository import RetentionRepository

router = APIRouter()

RETENTIONS_EXCEL_STRUCTURE = """
Estructura del Excel (hoja `ReteICA`):

| Columna | Obligatoria | Ejemplo | Descripcion |
| --- | --- | --- | --- |
| `codigo_municipio` | Si | `11001` | Codigo DANE del municipio. |
| `municipio` | No | `Bogota D.C.` | Nombre del municipio, para poder leer la tabla. |
| `concepto` | No | `servicios` | Actividad que fija la tarifa. Si se omite, `todos`. |
| `tarifa` | Si | `9.66` | Tarifa POR MIL (9.66 = 9,66 por mil = 0,966%), igual que SIIGO. |
| `base_uvt` | No | `4` | Tope en UVT por debajo del cual no se retiene. |

Un municipio puede traer varias filas, una por concepto (compra, servicios, honorarios...).
La clave de cada fila es (`codigo_municipio`, `concepto`).
"""


@router.get(
    "/integrations/retentions",
    response_model=list[RetentionResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar retenciones",
    description=(
        "Retorna las retenciones (ReteICA, ReteIVA, Retefuente, Autorretención) registradas "
        "en `integration_retentions`.\n\n"
        "Separada de `GET /integrations/taxes` (que ahora solo devuelve impuestos reales del "
        "documento: IVA, Impoconsumo, AdValorem). Cada fila `type=reteica` trae además su "
        "municipio, concepto y base mínima: es una opción completa por sí misma, no requiere "
        "cruzarse con ninguna otra tabla."
    ),
    response_description="Lista de retenciones, ordenadas por tipo y nombre.",
)
def list_retentions(
    active: Optional[bool] = Query(
        None, description="Filtrar por estado activo. Si se omite, retorna todas."
    ),
    type: Optional[str] = Query(
        None,
        description="Filtrar por tipo: retefuente | reteica | reteiva | autorretencion.",
        examples=["reteica"],
    ),
    repository: RetentionRepository = Depends(get_retention_repository),
) -> list[RetentionResponse]:
    return repository.list(active=active, type=type)


@router.post(
    "/integrations/retentions/imports",
    dependencies=[Depends(require_write)],
    response_model=ImportRetentionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Importar tarifas de ReteICA por municipio desde Excel",
    description=(
        "Recibe un archivo `.xlsx` con tarifas de ReteICA por municipio y las carga en "
        "`integration_retentions` (`type='reteica'`).\n\n"
        "Es la ÚNICA vía por la que el ReteICA entra al catálogo de retenciones: SIIGO no "
        "conoce municipios, así que el sync de SIIGO (`POST /integrations/retentions/"
        "siigo-syncs`) descarta cualquier fila ReteICA que le llegue.\n\n"
        f"{RETENTIONS_EXCEL_STRUCTURE}\n\n"
        "`replace=false` (por defecto) actualiza o agrega tarifas sin borrar las demás. "
        "`replace=true` reemplaza TODAS las filas ReteICA existentes por las del archivo "
        "(nunca toca ReteIVA/Retefuente/Autorretención, que vienen de SIIGO).\n\n"
        "Rechaza el archivo completo si mezcla tarifas por mil y en porcentaje: son la misma "
        "convención escrita de dos formas y aplicar una a la otra retiene diez veces de más "
        "o de menos."
    ),
    response_description="Cantidad de tarifas cargadas y catálogo de ReteICA resultante.",
    responses={
        400: {
            "description": (
                "Archivo inválido, columnas faltantes, filas duplicadas o unidades mezcladas."
            )
        },
    },
)
async def import_retentions_from_excel(
    file: UploadFile = File(..., description="Archivo Excel .xlsx con la hoja ReteICA."),
    replace: bool = Form(
        False,
        description="`false`: upsert por (municipio, concepto). `true`: reemplaza todo el ReteICA.",
    ),
    sheet_name: Optional[str] = Form(
        None, description="Nombre de hoja a leer. Si se omite, usa 'ReteICA'."
    ),
    use_case: ImportRetentionsUseCase = Depends(get_import_retentions_use_case),
) -> ImportRetentionsResponse:
    content = await file.read()
    return use_case.execute(file_content=content, replace=replace, sheet_name=sheet_name)


@router.post(
    "/integrations/retentions/siigo-syncs",
    dependencies=[Depends(require_write)],
    response_model=SyncSiigoRetentionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar retenciones desde SIIGO",
    description=(
        "Consulta `GET /v1/taxes` de SIIGO y reparte cada fila: impuestos a "
        "`integration_taxes`, retenciones (ReteIVA/Retefuente/Autorretención) a "
        "`integration_retentions`.\n\n"
        "**ReteICA se descarta.** SIIGO no conoce municipios: su ReteICA sincronizada es un "
        "porcentaje plano que no se puede verificar contra ningún municipio ni concepto real "
        "— reproducir eso en `integration_retentions` sería el mismo problema que motivó "
        "separar esta tabla. El ReteICA se carga solo por Excel "
        "(`POST /integrations/retentions/imports`).\n\n"
        "Es la MISMA sincronización que dispara `POST /integrations/taxes/siigo-syncs` — una "
        "sola llamada a SIIGO que reparte el resultado en las dos tablas; se expone también "
        "aquí por simetría con el recurso `retentions`, no como una segunda consulta a SIIGO."
    ),
    response_description="Resumen de impuestos y retenciones sincronizados.",
    responses={
        404: {"description": "No existe credencial activa para siigo con el account_key indicado."},
        502: {"description": "SIIGO no responde o retorna error."},
    },
)
def sync_retentions_from_siigo(
    use_case: SyncSiigoTaxesUseCase = Depends(get_sync_siigo_taxes_use_case),
) -> SyncSiigoRetentionsResponse:
    return use_case.execute()
