import hmac
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import NullPool, create_engine

from app.application.dto.purchase_invoice import SendPurchaseInvoiceRequest

router = APIRouter()


def _verify_internal_secret(x_internal_secret: str = Header(...)):
    expected = os.environ.get("INTERNAL_SECRET", "")
    if not expected or not hmac.compare_digest(x_internal_secret, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post(
    "/internal/provision-tenant",
    include_in_schema=False,
    dependencies=[Depends(_verify_internal_secret)],
)
def provision_tenant(tenant_slug: str):
    """Create all tables for this service in the tenant DB. Called by auth-service during tenant registration."""
    from app.infrastructure.config.database import Base

    user = os.environ["DATABASE_USER"]
    password = os.environ["DATABASE_PASSWORD"]
    host = os.environ["DATABASE_HOST"]
    port = os.environ.get("DATABASE_PORT", "5432")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/abacus_t_{tenant_slug}"
    engine = create_engine(url, poolclass=NullPool)
    Base.metadata.create_all(bind=engine, checkfirst=True)
    engine.dispose()
    return {
        "status": "provisioned",
        "tenant_slug": tenant_slug,
        "service": __import__("os").environ.get("SERVICE_NAME", "unknown"),
    }


# ── RF-05: contabilización desde la cola del xml-processor ─────────────────────
#
# Estas rutas existen porque la contabilización dejó de ocurrir dentro de la petición del
# usuario y pasó a una cola con workers. Un worker no tiene token de usuario: se despierta
# solo, quizá minutos después de que el documento se encolara y con el token del usuario ya
# vencido. Guardar ese token en la base para reutilizarlo sería peor que resolverlo aquí —un
# JWT persistido es un JWT que sobrevive al cierre de sesión de su dueño—.
#
# El patrón es el mismo que ya usan `rag-service` e `integration-config-service` para el
# trabajo en segundo plano: `X-Internal-Secret` autentica al servicio y `X-Tenant-Slug` dice
# contra qué empresa se opera. Son rutas internas (`include_in_schema=False`) y el gateway no
# las expone.


def _tenant_session(tenant_slug: str):
    from app.infrastructure.config.tenant_connection_manager import get_session_for_tenant

    return get_session_for_tenant(tenant_slug)


@router.post(
    "/internal/siigo/purchase-invoices",
    include_in_schema=False,
    dependencies=[Depends(_verify_internal_secret)],
)
def create_purchase_invoice_internal(
    request: SendPurchaseInvoiceRequest,
    x_tenant_slug: str = Header(...),
):
    """RF-05: crea la factura de compra para un worker de la cola.

    Comparte el caso de uso con la ruta pública, así que un documento se contabiliza
    exactamente igual venga del botón o de la cola. Duplicar la lógica aquí habría creado dos
    caminos capaces de divergir, y en una operación que crea asientos contables reales esa
    divergencia se paga con facturas mal formadas o duplicadas.

    El contrato de error es también el mismo: quien llama necesita `siigo_did_not_create`
    para saber si puede reenviar, y ese dato no puede depender de por qué puerta entró.
    """
    from app.adapters.api.routers.purchase_invoices import _http_status_for
    from app.application.use_cases.manage_credentials import ManageCredentialsUseCase
    from app.application.use_cases.send_purchase_invoice import SendPurchaseInvoiceUseCase
    from app.domain.exceptions.base import SiigoApiException, ValidationException
    from app.infrastructure.persistence.repositories.integration_repository import (
        IntegrationCredentialRepository,
    )

    db = _tenant_session(x_tenant_slug)
    try:
        use_case = SendPurchaseInvoiceUseCase(
            credentials=ManageCredentialsUseCase(IntegrationCredentialRepository(db))
        )
        return use_case.execute(request)
    except ValidationException as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except SiigoApiException as exc:
        raise HTTPException(
            status_code=_http_status_for(exc),
            detail={
                "message": exc.message,
                "siigo_status": exc.status_code,
                "siigo_error_codes": exc.error_codes,
                "retryable": exc.retryable,
                "siigo_did_not_create": exc.siigo_did_not_create,
                "duplicate": exc.is_duplicate,
            },
        ) from exc
    finally:
        db.close()


@router.get(
    "/internal/siigo/purchase-invoice-parameters",
    include_in_schema=False,
    dependencies=[Depends(_verify_internal_secret)],
)
def list_purchase_invoice_parameters_internal(
    x_tenant_slug: str = Header(...),
    account_key: Optional[str] = None,
):
    """RF-05: plantilla de parámetros para un worker de la cola.

    El worker la necesita antes de construir el cuerpo de la factura: es la fuente de los
    identificadores de catálogo que el documento de la DIAN no trae —el tipo de comprobante,
    la sucursal, la forma de pago por defecto— y que no pueden deducirse.
    """
    from app.application.use_cases.manage_purchase_invoice_parameters import (
        ManagePurchaseInvoiceParametersUseCase,
    )
    from app.infrastructure.persistence.repositories.purchase_invoice_parameter_repository import (
        PurchaseInvoiceParameterRepository,
    )

    db = _tenant_session(x_tenant_slug)
    try:
        use_case = ManagePurchaseInvoiceParametersUseCase(PurchaseInvoiceParameterRepository(db))
        return use_case.list(account_key=account_key)
    finally:
        db.close()
