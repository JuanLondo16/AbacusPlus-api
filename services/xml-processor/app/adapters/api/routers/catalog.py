from fastapi import APIRouter, Depends

from app.application.dto.catalog import (
    CostCenterResponse,
    PucAccountResponse,
    RetentionFuenteRateResponse,
    RetentionIcaRateResponse,
)
from app.dependencies import (
    get_cost_center_repo,
    get_puc_repo,
    get_retention_repo,
)
from app.infrastructure.persistence.repositories.cost_center_repository import CostCenterRepository
from app.infrastructure.persistence.repositories.puc_repository import PucRepository
from app.infrastructure.persistence.repositories.retention_repository import RetentionRepository

router = APIRouter()


@router.get(
    "/catalog/cost-centers",
    response_model=list[CostCenterResponse],
    summary="Listar centros de costo activos",
    description=(
        "Retorna todos los centros de costo activos configurados en el sistema. "
        "El llm-service los usa para que el LLM asigne centros de costo reales "
        "(en lugar de dejar `null`) al generar asientos contables de causación."
    ),
    response_description="Lista de centros de costo con código y nombre.",
)
def get_cost_centers(
    repo: CostCenterRepository = Depends(get_cost_center_repo),
):
    return [CostCenterResponse.model_validate(cc) for cc in repo.get_active()]


@router.get(
    "/catalog/puc-accounts",
    response_model=list[PucAccountResponse],
    summary="Listar cuentas PUC activas",
    description=(
        "Retorna todas las cuentas del Plan Único de Cuentas (PUC) marcadas como activas. "
        "El llm-service las inyecta en el contexto del LLM como catálogo de cuentas válidas, "
        "reduciendo la probabilidad de que el modelo invente códigos de cuenta inexistentes."
    ),
    response_description="Lista de cuentas PUC activas con código, nombre y nivel.",
)
def get_puc_accounts(
    repo: PucRepository = Depends(get_puc_repo),
):
    return [PucAccountResponse.model_validate(a) for a in repo.get_active()]


@router.get(
    "/catalog/retention-fuente-rates",
    response_model=list[RetentionFuenteRateResponse],
    summary="Listar tasas de retención en la fuente",
    description=(
        "Retorna las tasas de retención en la fuente configuradas por concepto y contribuyente. "
        "El llm-service las usa como referencia para determinar la subcuenta 2365xx correcta "
        "según el tipo de proveedor y bases mínimas (pesos y UVT). "
    ),
    response_description="Lista de tasas de reteFuente por concepto y contribuyente.",
)
def get_retention_fuente_rates(
    repo: RetentionRepository = Depends(get_retention_repo),
):
    items = repo.get_fuente_rates()
    return [
        RetentionFuenteRateResponse(
            retention_concept=r.retention_concept,
            taxpayer_type=r.taxpayer_type,
            minimum_base_uvt=float(r.minimum_base_uvt) if r.minimum_base_uvt is not None else None,
            minimum_base_pesos=float(r.minimum_base_pesos)
            if r.minimum_base_pesos is not None
            else None,
            rate_percentage=float(r.rate_percentage),
        )
        for r in items
    ]


@router.get(
    "/catalog/retention-ica-rates",
    response_model=list[RetentionIcaRateResponse],
    summary="Listar tasas de retención ICA por municipio",
    description=(
        "Retorna las tasas de reteICA configuradas por municipio (código DANE). "
        "Referencia para que el LLM calcule o valide el valor correcto de reteICA "
        "al generar asientos de causación de facturas locales."
    ),
    response_description="Lista de tasas de reteICA por código y nombre de municipio.",
)
def get_retention_ica_rates(
    repo: RetentionRepository = Depends(get_retention_repo),
):
    items = repo.get_ica_rates()
    return [
        RetentionIcaRateResponse(
            municipality_code=r.municipality_code,
            municipality_name=r.municipality_name,
            percentage=float(r.percentage),
        )
        for r in items
    ]
