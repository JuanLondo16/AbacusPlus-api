import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import NullPool, create_engine, text

from app.application.dto.fiscal_profile import FiscalProfileResponse
from app.application.dto.retention_criteria import RetentionCriteriaResponse
from app.application.dto.tax import TaxResponse
from app.application.use_cases.manage_fiscal_profile import ManageFiscalProfileUseCase
from app.application.use_cases.manage_retention_criteria import ManageRetentionCriteriaUseCase
from app.infrastructure.config.tenant_connection_manager import get_session_for_tenant
from app.infrastructure.persistence.repositories.retention_criteria_repository import (
    RetentionCriteriaRepository,
)
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository
from app.infrastructure.persistence.repositories.tenant_fiscal_profile_repository import (
    TenantFiscalProfileRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_internal_secret(x_internal_secret: str = Header(...)):
    expected = os.environ.get("INTERNAL_SECRET", "")
    if not expected or not hmac.compare_digest(x_internal_secret, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


def _autoseed_retention_criteria(tenant_slug: str) -> int:
    """RF-08: carga los criterios de partida solo si el tenant no tiene ninguno.

    NO destructivo, igual que el auto-seed de tarifas de ReteFuente del xml-processor: si el
    contador ya ajustó sus criterios, re-aprovisionar el cliente no los pisa. Así un tenant
    nuevo arranca con un cuestionario razonable en vez de con nada, y el que ya trabajó
    conserva su trabajo.

    Devuelve cuántos criterios se cargaron (0 si ya había).
    """
    from app.domain.services.retention_criteria_seed import (
        CRITERIOS_POR_DEFECTO,
        FUENTE_POR_DEFECTO,
    )
    from app.infrastructure.persistence.repositories.retention_criteria_repository import (
        RetentionCriteriaRepository,
    )

    db = get_session_for_tenant(tenant_slug)
    try:
        filas = [dict(c, activo=True, fuente=FUENTE_POR_DEFECTO) for c in CRITERIOS_POR_DEFECTO]
        cargados = RetentionCriteriaRepository(db).seed_if_empty(filas)
        if cargados:
            logger.info(
                "RF-08 auto-seed criterios tenant=%s: %d criterios cargados",
                tenant_slug,
                cargados,
            )
        return cargados
    except Exception as exc:  # noqa: BLE001
        # Un fallo aquí no puede impedir que el cliente quede aprovisionado: los criterios
        # son una fuente orientativa, no un requisito para operar.
        logger.warning("RF-08: no se pudieron sembrar los criterios (tenant=%s): %s", tenant_slug, exc)
        return 0
    finally:
        db.close()


@router.get(
    "/internal/retention-criteria",
    response_model=RetentionCriteriaResponse,
    include_in_schema=False,
    dependencies=[Depends(_verify_internal_secret)],
)
def get_retention_criteria_internal(x_tenant_slug: str = Header(...)) -> RetentionCriteriaResponse:
    """RF-08: criterios del contador para el llm-service (servicio-a-servicio).

    El llm-service no tiene JWT de usuario cuando sugiere retenciones en segundo plano:
    autentica con `X-Internal-Secret` y pasa el `X-Tenant-Slug`. Devuelve solo los activos,
    y los devuelve TODOS: no es una búsqueda por relevancia, son reglas que aplican a cada
    factura y deben entrar completas en cada decisión.
    """
    db = get_session_for_tenant(x_tenant_slug)
    try:
        return ManageRetentionCriteriaUseCase(RetentionCriteriaRepository(db)).get()
    finally:
        db.close()


@router.get(
    "/internal/fiscal-profile",
    response_model=FiscalProfileResponse,
    include_in_schema=False,
    dependencies=[Depends(_verify_internal_secret)],
)
def get_fiscal_profile_internal(x_tenant_slug: str = Header(...)) -> FiscalProfileResponse:
    """Perfil fiscal del tenant para el llm-service (servicio-a-servicio).

    El llm-service no tiene JWT de usuario al sugerir retenciones en background: autentica con
    `X-Internal-Secret` y pasa el `X-Tenant-Slug`. Devuelve el mismo perfil (o el default
    conservador) que la vía con token, para decidir si el comprador es agente de retención.
    """
    db = get_session_for_tenant(x_tenant_slug)
    try:
        return ManageFiscalProfileUseCase(TenantFiscalProfileRepository(db)).get()
    finally:
        db.close()


@router.get(
    "/internal/taxes",
    response_model=list[TaxResponse],
    include_in_schema=False,
    dependencies=[Depends(_verify_internal_secret)],
)
def get_taxes_internal(
    x_tenant_slug: str = Header(...),
    active: Optional[bool] = True,
) -> list[TaxResponse]:
    """Catálogo de impuestos para el xml-processor (servicio-a-servicio).

    La mayoría de los documentos entran por la descarga masiva desde la DIAN, que corre en
    segundo plano y no tiene JWT de usuario. Por esa vía, la consulta al catálogo por la ruta
    con token respondía 403 y el `except` del cliente la convertía en una lista vacía: cada
    línea quedaba sin `tax_id` y nadie se enteraba. En la base del cliente, de 152 líneas al
    19 % solo una había quedado enlazada.

    Se autentica igual que los otros endpoints internos —`X-Internal-Secret` y
    `X-Tenant-Slug`—, y no como ruta abierta: el catálogo describe la configuración tributaria
    de una empresa y el servicio es alcanzable desde la red del clúster.

    Por defecto devuelve solo los activos, que es lo que necesita quien va a enlazar una línea:
    un impuesto desactivado ya no debe asignarse a nada nuevo.
    """
    db = get_session_for_tenant(x_tenant_slug)
    try:
        return TaxRepository(db).list(active=active)
    finally:
        db.close()

def _migrate_tenant_db(engine) -> None:
    """Idempotent schema migrations. Safe to run on new or existing tenant DBs."""
    from app.infrastructure.config.database import Base

    Base.metadata.create_all(bind=engine, checkfirst=True)

    migrations = [
        # integration_cost_centers: drop legacy columns, add constraint, add new columns
        "ALTER TABLE integration_cost_centers DROP COLUMN IF EXISTS provider",
        "ALTER TABLE integration_cost_centers DROP COLUMN IF EXISTS account_key",
        "ALTER TABLE integration_cost_centers DROP CONSTRAINT IF EXISTS uq_cost_center_provider_key_code",
        (
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_cost_center_code') "
            "THEN ALTER TABLE integration_cost_centers ADD CONSTRAINT uq_cost_center_code UNIQUE (code); "
            "END IF; END $$"
        ),
        "ALTER TABLE integration_cost_centers ADD COLUMN IF NOT EXISTS external_id VARCHAR(120)",
        "ALTER TABLE integration_cost_centers ADD COLUMN IF NOT EXISTS raw_payload JSONB NOT NULL DEFAULT '{}'",
        "ALTER TABLE integration_cost_centers ADD COLUMN IF NOT EXISTS synced_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "ALTER TABLE integration_cost_centers ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "ALTER TABLE integration_cost_centers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        # integration_chart_accounts
        "ALTER TABLE integration_chart_accounts ADD COLUMN IF NOT EXISTS external_id VARCHAR(120)",
        "ALTER TABLE integration_chart_accounts ADD COLUMN IF NOT EXISTS account_type VARCHAR(80)",
        "ALTER TABLE integration_chart_accounts ADD COLUMN IF NOT EXISTS level INTEGER",
        "ALTER TABLE integration_chart_accounts ADD COLUMN IF NOT EXISTS parent_code VARCHAR(80)",
        "ALTER TABLE integration_chart_accounts ADD COLUMN IF NOT EXISTS accepts_movements BOOLEAN",
        "ALTER TABLE integration_chart_accounts ADD COLUMN IF NOT EXISTS raw_payload JSONB NOT NULL DEFAULT '{}'",
        "ALTER TABLE integration_chart_accounts ADD COLUMN IF NOT EXISTS synced_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "ALTER TABLE integration_chart_accounts ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "ALTER TABLE integration_chart_accounts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        # integration_products
        "ALTER TABLE integration_products ADD COLUMN IF NOT EXISTS raw_payload JSONB NOT NULL DEFAULT '{}'",
        "ALTER TABLE integration_products ADD COLUMN IF NOT EXISTS synced_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "ALTER TABLE integration_products ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "ALTER TABLE integration_products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        # integration_payment_types
        "ALTER TABLE integration_payment_types ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "ALTER TABLE integration_payment_types ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        # integration_taxes
        "ALTER TABLE integration_taxes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "ALTER TABLE integration_taxes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        # tenant_fiscal_profile: los municipios de ICA se llevaban aquí y también en
        # `retention_ica_rates`, que es la única tabla que además guarda la TARIFA. Dos listas
        # de lo mismo solo podían coincidir (redundancia) o discrepar (un municipio sin tarifa
        # no habilita ReteICA, y uno con tarifa fuera de esta lista quedaba invisible para el
        # modelo). Se conserva una: la que sirve para calcular.
        "ALTER TABLE tenant_fiscal_profile DROP COLUMN IF EXISTS municipios",
    ]

    with engine.connect() as conn:
        for sql in migrations:
            conn.execute(text(sql))
        conn.commit()


@router.post(
    "/internal/provision-tenant",
    include_in_schema=False,
    dependencies=[Depends(_verify_internal_secret)],
)
def provision_tenant(tenant_slug: str):
    """Create/migrate all tables for this service in the tenant DB. Safe to re-run on existing tenants."""
    user = os.environ["DATABASE_USER"]
    password = os.environ["DATABASE_PASSWORD"]
    host = os.environ["DATABASE_HOST"]
    port = os.environ.get("DATABASE_PORT", "5432")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/abacus_t_{tenant_slug}"
    engine = create_engine(url, poolclass=NullPool)
    _migrate_tenant_db(engine)
    engine.dispose()
    seeded = _autoseed_retention_criteria(tenant_slug)
    return {
        "status": "provisioned",
        "retention_criteria_seeded": seeded,
        "tenant_slug": tenant_slug,
        "service": os.environ.get("SERVICE_NAME", "unknown"),
    }
