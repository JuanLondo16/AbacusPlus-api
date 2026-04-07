from pydantic import BaseModel, Field


class AIAnalyzeRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        description="Prompt a enviar a OpenAI. Puede ser una pregunta, instrucción o texto a analizar.",
        examples=["¿Qué tipo de factura es la número FE7674 emitida por Monster Cakes?"],
    )
    model: str = Field(
        default="gpt-4o-mini",
        description="Modelo de OpenAI a utilizar.",
        examples=["gpt-4o-mini", "gpt-4o"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "prompt": "Clasifica si el siguiente texto corresponde a una factura de servicios o de productos: torta pie de limón 4 porciones.",
                "model": "gpt-4o-mini",
            }
        }
    }


class AIUsage(BaseModel):
    prompt_tokens: int = Field(..., description="Tokens consumidos por el prompt.")
    completion_tokens: int = Field(..., description="Tokens consumidos por la respuesta generada.")
    total_tokens: int = Field(..., description="Total de tokens consumidos en la llamada.")


class AIAnalyzeResponse(BaseModel):
    response: str = Field(..., description="Texto de respuesta generado por el modelo.")
    model: str = Field(..., description="Modelo de OpenAI que procesó la solicitud.")
    prompt: str = Field(..., description="Prompt original enviado.")
    usage: AIUsage = Field(..., description="Métricas de consumo de tokens.")
