import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.application.dto.rule import (
    ApprovalNotification,
    CreateRuleRequest,
    RuleResponse,
    RuleStatsResponse,
    UpdateRuleRequest,
)
from app.application.use_cases.compute_rule_stats import ComputeRuleStatsUseCase
from app.application.use_cases.record_approved_entry import RecordApprovedEntryUseCase
from app.dependencies import (
    get_compute_rule_stats_use_case,
    get_record_approved_entry_use_case,
    get_rule_repository,
)
from app.domain.entities.accounting_rule import AccountingRule
from app.infrastructure.config.auth_dependency import get_tenant_db

router = APIRouter()
logger = logging.getLogger(__name__)


def _rule_to_response(rule: AccountingRule) -> RuleResponse:
    return RuleResponse(
        id=rule.id,
        match_key_type=rule.match_key_type,
        issuer_nit=rule.issuer_nit,
        ciiu_code=rule.ciiu_code,
        item_keywords=rule.item_keywords,
        suggested_debit_account=rule.suggested_debit_account,
        suggested_credit_account=rule.suggested_credit_account,
        suggested_tax_accounts=rule.suggested_tax_accounts,
        suggested_cost_center=rule.suggested_cost_center,
        confidence_score=rule.confidence_score,
        approval_count=rule.approval_count,
        edit_count=rule.edit_count,
        last_approved_at=rule.last_approved_at,
        is_active=rule.is_active,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.post(
    "/rules",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear regla de causación manual",
    description=(
        "Crea una nueva regla de causación de forma manual.\n\n"
        "Las reglas se crean automáticamente al aprobar documentos vía `POST /rules/approvals`. "
        "Este endpoint permite crear reglas basadas en conocimiento experto sin esperar aprobaciones.\n\n"
        "**Tipos de clave de matching:**\n"
        "- `nit_semantic`: matching por NIT + similitud semántica del ítem (requiere Ollama).\n"
        "- `nit_only`: regla genérica para un proveedor sin importar la descripción del ítem.\n"
        "- `keyword_only`: matching por palabras clave sin NIT (categoría de producto/servicio)."
    ),
    response_description="Regla creada con su ID y metadatos.",
    responses={
        422: {"description": "Datos inválidos o tipo de matching desconocido."},
    },
)
def create_rule(
    request: CreateRuleRequest,
    db: Session = Depends(get_tenant_db),
    rule_repo=Depends(get_rule_repository),
) -> RuleResponse:
    valid_types = {"nit_semantic", "nit_only", "keyword_only"}
    if request.match_key_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"match_key_type debe ser uno de: {', '.join(valid_types)}",
        )
    rule = AccountingRule(
        match_key_type=request.match_key_type,
        issuer_nit=request.issuer_nit,
        item_keywords=request.item_keywords,
        suggested_debit_account=request.suggested_debit_account,
        suggested_credit_account=request.suggested_credit_account,
        suggested_tax_accounts=request.suggested_tax_accounts or {},
        suggested_cost_center=request.suggested_cost_center,
        confidence_score=request.confidence_score,
    )
    created = rule_repo.create(rule)
    return _rule_to_response(created)


@router.get(
    "/rules",
    response_model=list[RuleResponse],
    summary="Listar reglas de causación",
    description=(
        "Lista todas las reglas de causación del sistema con filtros opcionales.\n\n"
        "Ordenadas por `confidence_score` descendente."
    ),
    response_description="Lista de reglas.",
)
def list_rules(
    nit: Optional[str] = Query(None, description="Filtrar por NIT del emisor."),
    match_key_type: Optional[str] = Query(
        None, description="Filtrar por tipo: `nit_semantic` | `nit_only` | `keyword_only`."
    ),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Confianza mínima."),
    is_active: Optional[bool] = Query(None, description="Filtrar por estado activo/inactivo."),
    rule_repo=Depends(get_rule_repository),
) -> list[RuleResponse]:
    rules = rule_repo.list(
        nit=nit,
        match_key_type=match_key_type,
        min_confidence=min_confidence,
        is_active=is_active,
    )
    return [_rule_to_response(r) for r in rules]


@router.patch(
    "/rules/{rule_id}",
    response_model=RuleResponse,
    summary="Actualizar regla de causación",
    description=(
        "Actualiza una regla existente. Permite activar/desactivar y ajustar manualmente "
        "el score de confianza.\n\n"
        "Solo los campos enviados en el body son modificados."
    ),
    response_description="Regla actualizada.",
    responses={
        404: {"description": "Regla no encontrada."},
    },
)
def update_rule(
    rule_id: int,
    request: UpdateRuleRequest,
    rule_repo=Depends(get_rule_repository),
) -> RuleResponse:
    rule = rule_repo.get_by_id(rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule {rule_id} not found"
        )
    if request.is_active is not None:
        rule.is_active = request.is_active
    if request.confidence_score is not None:
        rule.confidence_score = request.confidence_score
    updated = rule_repo.update(rule)
    return _rule_to_response(updated)


@router.get(
    "/rules/stats",
    response_model=RuleStatsResponse,
    summary="Métricas globales del sistema de reglas",
    description=(
        "Retorna métricas de precisión y cobertura del sistema de reglas:\n\n"
        "- **hit_rate**: proporción de lookups que retornaron HIT (confianza ≥ 0.85).\n"
        "- **precision**: de los lookups con contexto (HIT/PARTIAL), cuántos terminaron "
        "aprobados sin corrección por el contador.\n"
        "- **miss_rate**: proporción de lookups sin historial suficiente.\n\n"
        "Útil para monitorear si el sistema está aprendiendo correctamente."
    ),
    response_description="Métricas globales del sistema de reglas.",
)
def get_stats(
    use_case: ComputeRuleStatsUseCase = Depends(get_compute_rule_stats_use_case),
) -> RuleStatsResponse:
    return use_case.execute()


@router.post(
    "/rules/approvals",
    status_code=status.HTTP_200_OK,
    summary="Registrar aprobación de asiento contable",
    description=(
        "Recibe la notificación de que un contador aprobó un asiento contable "
        "(`PATCH /documents/{id}/approve` en xml-processor).\n\n"
        "**Lógica de aprendizaje:**\n"
        "- Si hubo un HIT/PARTIAL previo y el asiento aprobado coincide → refuerza la regla "
        "(`confidence += 0.05`).\n"
        "- Si el contador editó el asiento antes de aprobar → penaliza la regla anterior "
        "(`confidence -= 0.15`) y crea una nueva regla con los valores correctos.\n"
        "- Si fue MISS → crea una nueva regla con `confidence = 0.60`.\n\n"
        "Este endpoint es llamado **best-effort** por xml-processor; no bloquea la aprobación."
    ),
    response_description="Acción tomada: `reinforced`, `created` o `skipped`.",
    responses={
        422: {"description": "Datos de aprobación inválidos."},
    },
)
async def record_approval(
    notification: ApprovalNotification,
    use_case: RecordApprovedEntryUseCase = Depends(get_record_approved_entry_use_case),
) -> dict:
    return await use_case.execute(notification)
