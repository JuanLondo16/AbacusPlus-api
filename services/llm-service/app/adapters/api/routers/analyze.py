from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.dto.ai import AIAnalyzeRequest, AIAnalyzeResponse
from app.application.use_cases.analyze_with_ai import AnalyzeWithAIUseCase
from app.dependencies import get_analyze_with_ai_use_case
from app.infrastructure.config.auth_dependency import TokenData, get_token_data

router = APIRouter()


@router.post(
    "/analyses",
    response_model=AIAnalyzeResponse,
    summary="Análisis directo con OpenAI (sin RAG)",
    description=(
        "Envía un prompt directamente a OpenAI sin enriquecer con contexto RAG. "
        "Útil para análisis generales, clasificaciones o preguntas que no requieren "
        "contexto específico de las facturas almacenadas.\n\n"
        "Para consultas relacionadas con facturas indexadas, usar `POST /api/v1/query` "
        "que incorpora contexto RAG automáticamente."
    ),
    response_description="Respuesta del modelo con el texto generado y métricas de uso de tokens.",
    responses={
        502: {"description": "Error de comunicación con la API de OpenAI."},
    },
)
async def analyze_with_ai(
    request: AIAnalyzeRequest,
    _: Annotated[TokenData, Depends(get_token_data)],
    use_case: AnalyzeWithAIUseCase = Depends(get_analyze_with_ai_use_case),
):
    return await use_case.execute(request)
