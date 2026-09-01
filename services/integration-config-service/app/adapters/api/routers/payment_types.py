from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from openpyxl import Workbook

from app.adapters.api.routers._excel_template import style_header, xlsx_response
from app.application.dto.payment_type import (
    ImportPaymentTypesResponse,
    PaymentTypeResponse,
)
from app.application.use_cases.import_payment_types import ImportPaymentTypesUseCase
from app.application.use_cases.sync_siigo_payment_types import SyncSiigoPaymentTypesUseCase
from app.dependencies import (
    get_import_payment_types_use_case,
    get_payment_type_repository,
    get_sync_siigo_payment_types_use_case,
)
from app.infrastructure.config.auth_dependency import require_write
from app.infrastructure.persistence.repositories.payment_type_repository import (
    PaymentTypeRepository,
)

router = APIRouter()

PAYMENT_TYPES_EXCEL_STRUCTURE = """
Estructura del Excel:

| Columna | Obligatoria | Ejemplo | Descripcion |
| --- | --- | --- | --- |
| `nombre` | Si | `Transferencia bancaria` | Nombre del tipo de pago. |
| `tipo` | Si | `electronico` | Categoria del tipo de pago. |
| `activo` | No | `true` | Estado. Si se omite, queda `true`. |

`name`, `type` y `active` tambien se aceptan como alias: son el encabezado en ingles con
que este endpoint funciono antes de que la plantilla pasara a espanol.

Valores booleanos aceptados: `true`, `false`, `1`, `0`, `yes`, `no`, `si`, `sí`, `x`.
"""


@router.get(
    "/integrations/payment-types",
    response_model=list[PaymentTypeResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar tipos de pago",
    description=(
        "Retorna todos los tipos de pago registrados en la tabla local `integration_payment_types`.\n\n"
        "Usa el filtro `active` para obtener solo los activos o solo los inactivos."
    ),
    response_description="Lista de tipos de pago ordenados por nombre.",
    responses={},
)
def list_payment_types(
    active: Optional[bool] = Query(
        None, description="Filtrar por estado activo. Si se omite, retorna todos."
    ),
    repository: PaymentTypeRepository = Depends(get_payment_type_repository),
) -> list[PaymentTypeResponse]:
    return repository.list(active=active)


@router.post(
    "/integrations/payment-types/imports",
    dependencies=[Depends(require_write)],
    response_model=ImportPaymentTypesResponse,
    status_code=status.HTTP_200_OK,
    summary="Importar tipos de pago desde Excel",
    description=(
        "Recibe un archivo `.xlsx` con tipos de pago y alimenta "
        "la tabla local `integration_payment_types`.\n\n"
        "La operacion es idempotente por `name`: si el tipo ya existe, "
        "actualiza sus datos; si no existe, lo crea.\n\n"
        f"{PAYMENT_TYPES_EXCEL_STRUCTURE}"
    ),
    response_description="Resumen de tipos importados y listado resultante.",
    responses={
        400: {"description": "Archivo invalido, columnas faltantes o filas con datos incorrectos."},
    },
)
async def import_payment_types_from_excel(
    sheet_name: Optional[str] = Form(
        None, description="Nombre de hoja a leer. Si se omite, usa la primera hoja."
    ),
    file: UploadFile = File(..., description="Archivo Excel .xlsx con los tipos de pago."),
    mode: str = Form(
        "upsert",
        description=(
            "`upsert`: actualiza tipos de pago existentes y agrega nuevos (no elimina). "
            "`replace`: elimina todos los tipos de pago actuales (incluidos los "
            "sincronizados desde SIIGO) antes de importar."
        ),
        examples=["upsert"],
    ),
    use_case: ImportPaymentTypesUseCase = Depends(get_import_payment_types_use_case),
) -> ImportPaymentTypesResponse:
    content = await file.read()
    return use_case.execute(sheet_name=sheet_name, file_content=content, mode=mode)


@router.get(
    "/integrations/payment-types/template",
    summary="Descargar plantilla Excel de tipos de pago",
    description=(
        "Genera un `.xlsx` listo para llenar y volver a importar via "
        "`POST /integrations/payment-types/imports`.\n\n"
        "La hoja llega solo con encabezados: los tipos de pago son propios de cada "
        "empresa y no existe una tabla estandar que precargar.\n\n"
        f"{PAYMENT_TYPES_EXCEL_STRUCTURE}"
    ),
    response_description="Archivo .xlsx de plantilla.",
)
def download_payment_types_template():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Tipos de pago"
    sheet.append(["nombre", "tipo", "activo"])
    style_header(
        sheet,
        notes={
            "nombre": "Nombre del tipo de pago, como aparecera en el selector.",
            "tipo": "Categoria del tipo de pago (por ejemplo: efectivo, electronico).",
            "activo": "Opcional. true/false. Si se omite, queda true.",
        },
        widths={"A": 26, "B": 18, "C": 10},
    )
    return xlsx_response(workbook, "plantilla-tipos-pago.xlsx")


@router.post(
    "/integrations/payment-types/siigo-syncs",
    dependencies=[Depends(require_write)],
    response_model=ImportPaymentTypesResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar tipos de pago desde SIIGO",
    description=(
        "Consulta el endpoint `GET /v1/payment-types` de la API de SIIGO y sincroniza "
        "los resultados en la tabla local `integration_payment_types`.\n\n"
        "Usa la primera credencial activa del proveedor `siigo` registrada en el sistema. "
        "El parametro `document_type` se lee desde `extra_config.default_document_type` "
        "de esa credencial. Si no está configurado, usa `FC` por defecto.\n\n"
        "La operacion es idempotente por `name`: actualiza si ya existe, crea si no.\n\n"
        "Si el token de acceso ha expirado o no existe, autentica automaticamente contra SIIGO "
        "y persiste el nuevo token antes de hacer la consulta."
    ),
    response_description="Resumen de tipos sincronizados y listado resultante.",
    responses={
        404: {"description": "No existe credencial activa para siigo con el account_key indicado."},
        502: {"description": "SIIGO no responde o retorna error."},
    },
)
def sync_payment_types_from_siigo(
    use_case: SyncSiigoPaymentTypesUseCase = Depends(get_sync_siigo_payment_types_use_case),
) -> ImportPaymentTypesResponse:
    return use_case.execute()
