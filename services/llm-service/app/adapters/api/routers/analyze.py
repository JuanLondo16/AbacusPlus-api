from fastapi import APIRouter, Depends
from app.application.dto.ai import AIAnalyzeRequest, AIAnalyzeResponse
from app.application.use_cases.analyze_with_ai import AnalyzeWithAIUseCase
from app.dependencies import get_analyze_with_ai_use_case

router = APIRouter()


@router.post("/ai/analyze", response_model=AIAnalyzeResponse)
async def analyze_with_ai(
    request: AIAnalyzeRequest,
    use_case: AnalyzeWithAIUseCase = Depends(get_analyze_with_ai_use_case),
):
    """Envía un prompt directo a OpenAI sin contexto RAG."""
    return await use_case.execute(request)
