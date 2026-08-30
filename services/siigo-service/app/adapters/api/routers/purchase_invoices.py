"""RF-05: creación de la factura de compra en SIIGO.

Este router es deliberadamente delgado y **sin estado**: recibe los datos ya mapeados, llama
a SIIGO y devuelve el resultado. No conoce el documento de la DIAN ni su estado, porque el
dueño del ciclo de vida del documento es el xml-processor. Esa separación es la que permite
que el estado «Contabilizando» quede confirmado en la base antes de que esta llamada ocurra.
"""

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.dto.purchase_invoice import (
    FindPurchaseInvoiceResponse,
    SendPurchaseInvoiceRequest,
    SendPurchaseInvoiceResponse,
)
from app.application.use_cases.find_purchase_invoice import FindPurchaseInvoiceUseCase
from app.application.use_cases.send_purchase_invoice import SendPurchaseInvoiceUseCase
from app.dependencies import (
    get_find_purchase_invoice_use_case,
    get_send_purchase_invoice_use_case,
)
from app.domain.exceptions.base import SiigoApiException, ValidationException
from app.infrastructure.config.auth_dependency import require_write

router = APIRouter()


@router.post(
    "/siigo/purchase-invoices",
    dependencies=[Depends(require_write)],
    response_model=SendPurchaseInvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear factura de compra en SIIGO",
    description=(
        "Crea una factura de compra o gasto en SIIGO Nube (`POST /v1/purchases`).\n\n"
        "**Por qué este endpoint y no `/v1/journals`:** la factura de compra es el "
        "comprobante que admite forma de pago (SIIGO la usa para generar la cuenta por "
        "pagar), retenciones a nivel de documento y centro de costo general — los tres "
        "requeridos por el alcance del proyecto. `/v1/journals` no expone ninguno de los "
        "tres y obligaría a construir el asiento cuadrado, que se delega a SIIGO.\n\n"
        "**Flujo:**\n"
        "1. Valida la información obligatoria ANTES de llamar a SIIGO.\n"
        "2. Renueva el token de SIIGO si está vencido.\n"
        "3. Construye el JSON conforme al contrato oficial y lo envía.\n"
        "4. Exige que la respuesta traiga el `id`; sin él, no se da por exitosa.\n\n"
        "**Advertencia de duplicidad:** SIIGO **no admite `Idempotency-Key` en este "
        "endpoint** (solo en facturas de venta, notas crédito, comprobantes contables y "
        "recibos de caja). Por eso quien llama debe garantizar que el documento no se envíe "
        "dos veces; ante un `504` o un error de red, la factura pudo quedar creada y hay que "
        "verificar en SIIGO antes de reenviar.\n\n"
        "**Prerrequisitos:** credenciales de SIIGO registradas y los identificadores de "
        "catálogo (`document_id`, `payment_id`, `cost_center`, impuestos) que provienen de "
        "la plantilla `purchase-invoice-parameters` y de los catálogos sincronizados."
    ),
    response_description="Factura de compra creada en SIIGO, con su id y consecutivo.",
    responses={
        422: {"description": "Falta información obligatoria; no se llamó a SIIGO."},
        401: {"description": "Credenciales de SIIGO inválidas o token no renovable."},
        404: {"description": "No existe credencial activa para el account_key indicado."},
        409: {"description": "SIIGO reporta que el comprobante ya existe (duplicated_document)."},
        429: {"description": "Se superó el límite de 100 peticiones por minuto de SIIGO."},
        502: {"description": "SIIGO no disponible o respuesta inesperada."},
    },
)
def create_purchase_invoice(
    request: SendPurchaseInvoiceRequest,
    use_case: SendPurchaseInvoiceUseCase = Depends(get_send_purchase_invoice_use_case),
) -> SendPurchaseInvoiceResponse:
    try:
        return use_case.execute(request)
    except ValidationException as exc:
        # 422 y no 400: el documento está incompleto de nuestro lado y SIIGO ni se llamó.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message
        ) from exc
    except SiigoApiException as exc:
        raise HTTPException(
            status_code=_http_status_for(exc),
            detail={
                "message": exc.message,
                "siigo_status": exc.status_code,
                "siigo_error_codes": exc.error_codes,
                # `retryable`: ¿tiene sentido repetir esta misma petición automáticamente?
                "retryable": exc.retryable,
                # `siigo_did_not_create`: ¿consta que SIIGO no creó el comprobante? Es lo que
                # necesita quien orquesta para decidir si el documento puede volver a
                # enviarse tras corregirlo, o si hay que verificar en SIIGO antes de tocarlo.
                "siigo_did_not_create": exc.siigo_did_not_create,
                "duplicate": exc.is_duplicate,
            },
        ) from exc


@router.get(
    "/siigo/purchase-invoices",
    response_model=FindPurchaseInvoiceResponse,
    summary="Buscar en SIIGO una factura de compra ya creada",
    description=(
        "Consulta `GET /v1/purchases` para averiguar si una factura de compra existe ya en "
        "SIIGO, identificándola por el número de factura del proveedor.\n\n"
        "**Para qué sirve (RF-06):** cuando la contabilización termina en timeout o error de "
        "red, no se sabe si SIIGO llegó a crear la factura, y el documento queda bloqueado en "
        "«Contabilizando». Reenviarlo a ciegas podría duplicar un asiento real, porque "
        "`/v1/purchases` **no admite `Idempotency-Key`**. Este endpoint es la forma de salir "
        "de esa duda preguntándole a SIIGO.\n\n"
        "**Cómo busca:** SIIGO permite filtrar por rango de fechas de creación, pero no por "
        "el número de factura del proveedor. Se acota entonces por fecha (±2 días alrededor "
        "de la del documento, para absorber desfases) y la coincidencia por número se "
        "resuelve sobre el resultado.\n\n"
        "**Lectura del resultado:** una lista `matches` vacía significa que SIIGO no creó "
        "nada y que el documento puede reenviarse sin riesgo. Una coincidencia trae el "
        "`siigo_id` con el que cerrar el documento sin volver a enviarlo."
    ),
    response_description="Facturas de SIIGO que coinciden con el número buscado.",
    responses={
        401: {"description": "Credenciales de SIIGO inválidas o token no renovable."},
        404: {"description": "No existe credencial activa para el account_key indicado."},
        422: {"description": "No se indicó el número de factura del proveedor."},
        502: {"description": "SIIGO no disponible o respuesta inesperada."},
    },
)
def find_purchase_invoices(
    provider_invoice_number: str = Query(
        ...,
        description=(
            "Número de la factura del proveedor tal como se registró al contabilizar. "
            "Es el dato que identifica al documento de la DIAN dentro de SIIGO."
        ),
        examples=["FE1234"],
    ),
    document_date: Optional[date_type] = Query(
        None,
        description=(
            "Fecha del documento. Acota la búsqueda a ±2 días y evita barrer el histórico "
            "completo, que consumiría el cupo de 100 peticiones por minuto de SIIGO."
        ),
    ),
    account_key: Optional[str] = Query(
        None, description="Empresa de SIIGO contra la que consultar. Por defecto, la activa."
    ),
    use_case: FindPurchaseInvoiceUseCase = Depends(get_find_purchase_invoice_use_case),
) -> FindPurchaseInvoiceResponse:
    try:
        return use_case.execute(
            account_key=account_key,
            provider_invoice_number=provider_invoice_number,
            document_date=document_date,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ValidationException as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message
        ) from exc
    except SiigoApiException as exc:
        raise HTTPException(
            status_code=_http_status_for(exc),
            detail={"message": exc.message, "siigo_status": exc.status_code},
        ) from exc


def _http_status_for(exc: SiigoApiException) -> int:
    """Traduce el fallo de SIIGO al código que debe ver quien orquesta.

    Los códigos que el cliente puede accionar (401, 403, 404, 409, 429) se propagan tal cual
    para que la capa superior distinga «corrige las credenciales» de «espera y reintenta».
    El resto se agrupa en 502, porque desde el punto de vista de esta API el fallo es de un
    tercero, no de la petición recibida.
    """
    if exc.is_duplicate:
        return status.HTTP_409_CONFLICT
    if exc.status_code in (401, 403, 404, 409, 429):
        return exc.status_code
    if exc.status_code == 400:
        # SIIGO rechazó los datos: es un problema del documento, no de disponibilidad.
        return status.HTTP_422_UNPROCESSABLE_ENTITY
    return status.HTTP_502_BAD_GATEWAY
