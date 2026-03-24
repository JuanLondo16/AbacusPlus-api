from app.domain.ports.services import AIServicePort
from app.application.dto.ai import AIAnalyzeRequest, AIAnalyzeResponse


class AnalyzeWithAIUseCase:
    def __init__(self, ai_service: AIServicePort):
        self._ai_service = ai_service

    async def execute(self, request: AIAnalyzeRequest) -> AIAnalyzeResponse:
        result = await self._ai_service.complete(prompt=request.prompt, model=request.model)
        return AIAnalyzeResponse(
            response=result["content"],
            model=request.model,
            prompt=request.prompt,
            usage=result["usage"],
        )
