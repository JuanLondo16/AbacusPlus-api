from fastapi import APIRouter, Depends, status

from app.application.dto.lookup import LookupRequest, LookupResponse
from app.application.use_cases.lookup_rules import LookupRulesUseCase
from app.dependencies import get_lookup_rules_use_case

router = APIRouter()


@router.post(
    "/rules/lookups",
    response_model=LookupResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultar reglas de causación antes de llamar al LLM",
    description=(
        "Consulta el historial de causaciones aprobadas para los ítems de un documento, "
        "retornando un nivel de confianza que el `llm-service` usa para enriquecer el prompt.\n\n"
        "**Niveles de respuesta:**\n"
        "- **HIT** (`confidence ≥ 0.85`): causación completa conocida. llm-service incluye la "
        "propuesta como 'causación sugerida por historial aprobado, valida y ajusta si es necesario'.\n"
        "- **PARTIAL** (`0.50 ≤ confidence < 0.85`): partes conocidas (ej: cuenta de gasto sí, "
        "retención no). llm-service incluye lo conocido y pide al LLM completar lo que falta.\n"
        "- **MISS** (`confidence < 0.50`): sin historial suficiente. llm-service llama al LLM "
        "sin contexto adicional.\n\n"
        "**Cascada de matching (de más específico a más general):**\n"
        "1. `nit_semantic`: NIT emisor + similitud semántica de la descripción (Ollama).\n"
        "2. `nit_only`: regla genérica del proveedor por NIT.\n"
        "3. `keyword_only`: palabras clave de la descripción sin NIT.\n\n"
        "Se usa `POST` con body porque los parámetros de búsqueda incluyen listas de ítems "
        "que excederían los límites de URL (RFC 9110 §9.3.1).\n\n"
        "Si se provee `document_id`, el lookup queda registrado en `rule_match_attempts` "
        "para calcular métricas de precisión y detectar ediciones posteriores."
    ),
    response_description="Nivel de coincidencia, causación sugerida y explicación.",
    responses={
        502: {"description": "Error de comunicación con Ollama al generar embeddings."},
    },
)
async def lookup_rules(
    request: LookupRequest,
    use_case: LookupRulesUseCase = Depends(get_lookup_rules_use_case),
) -> LookupResponse:
    return await use_case.execute(request)
