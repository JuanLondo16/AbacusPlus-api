from fastapi import APIRouter, Depends, Query, status

from app.application.dto.retention_criteria import (
    RetentionCriteriaReplaceRequest,
    RetentionCriteriaResponse,
)
from app.application.use_cases.manage_retention_criteria import ManageRetentionCriteriaUseCase
from app.dependencies import get_retention_criteria_use_case
from app.infrastructure.config.auth_dependency import require_write

router = APIRouter()


@router.get(
    "/integrations/retention-criteria",
    response_model=RetentionCriteriaResponse,
    status_code=status.HTTP_200_OK,
    summary="Criterios de retención del contador",
    description=(
        "**RF-08.** Criterios con los que el contador de esta empresa determina las "
        "retenciones: cómo identifica el concepto de ReteFuente, cuándo procede ReteICA, qué "
        "condiciones del proveedor impiden retener, etc.\n\n"
        "Alimentan el prompt de la sugerencia automática como fuente **orientativa**: pesan "
        "más que una deducción del modelo y menos que una tarifa oficial cargada o el perfil "
        "fiscal, que son vinculantes.\n\n"
        "**Son datos por empresa, no una configuración global.** Cada contador tiene sus "
        "criterios y estos cambian con la norma o con su interpretación; por eso viven en la "
        "base de cada cliente, igual que su perfil fiscal, y se editan sin desplegar.\n\n"
        "Al aprovisionar un cliente se cargan unos criterios de partida que deben revisarse "
        "con su contador."
    ),
    response_description="Criterios vigentes del tenant.",
)
def get_retention_criteria(
    include_inactive: bool = Query(
        False,
        description=(
            "Incluye los criterios desactivados. Útil para revisarlos en la interfaz; el "
            "llm-service solo consume los activos."
        ),
    ),
    use_case: ManageRetentionCriteriaUseCase = Depends(get_retention_criteria_use_case),
) -> RetentionCriteriaResponse:
    return use_case.get(only_active=not include_inactive)


@router.put(
    "/integrations/retention-criteria",
    dependencies=[Depends(require_write)],
    response_model=RetentionCriteriaResponse,
    status_code=status.HTTP_200_OK,
    summary="Reemplazar los criterios de retención",
    description=(
        "**RF-08.** Reemplaza el conjunto completo de criterios del tenant.\n\n"
        "**Por qué en bloque y no uno a uno:** el contador revisa sus criterios como un "
        "cuerpo único —el cuestionario completo—, no como registros sueltos. Editar uno sin "
        "ver los demás es precisamente como se introducen contradicciones entre ellos.\n\n"
        "Los criterios enviados quedan vigentes de inmediato para las siguientes sugerencias: "
        "no requiere despliegue ni reinicio."
    ),
    response_description="Criterios que quedaron vigentes.",
    responses={422: {"description": "Un criterio tiene un tema no admitido o campos vacíos."}},
)
def replace_retention_criteria(
    request: RetentionCriteriaReplaceRequest,
    use_case: ManageRetentionCriteriaUseCase = Depends(get_retention_criteria_use_case),
) -> RetentionCriteriaResponse:
    return use_case.replace(request)
