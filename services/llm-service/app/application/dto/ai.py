from pydantic import BaseModel, Field


class AIAnalyzeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str = Field(default="gpt-4o-mini")


class AIUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AIAnalyzeResponse(BaseModel):
    response: str
    model: str
    prompt: str
    usage: AIUsage
