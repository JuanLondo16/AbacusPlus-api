import logging
from typing import Any, Optional
from openai import AsyncOpenAI
from app.domain.ports.services import AIServicePort

logger = logging.getLogger(__name__)


class OpenAIService(AIServicePort):
    def __init__(self, api_key: str):
        self._client = AsyncOpenAI(api_key=api_key)

    async def complete(
        self,
        prompt: str,
        model: str = "gpt-4o-mini",
        system_prompt: Optional[str] = None,
        *,
        temperature: Optional[float] = None,
        json_schema: Optional[dict[str, Any]] = None,
    ) -> dict:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        create_kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            create_kwargs["temperature"] = temperature

        # Si se provee un JSON schema, exigimos salida estructurada (JSON estricto).
        # Algunos modelos/SDKs pueden no soportarlo; en ese caso degradamos a salida libre.
        if json_schema is not None:
            try:
                create_kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": json_schema,
                }
            except Exception:
                # fallback silencioso: dejamos salida libre
                pass

        try:
            response = await self._client.chat.completions.create(**create_kwargs)
        except Exception as exc:
            # Fallback: si el modelo o la cuenta no soportan json_schema, reintenta sin response_format.
            if json_schema is not None and "response_format" in create_kwargs:
                logger.warning("OpenAI rechazó response_format json_schema; reintentando sin schema: %s", exc)
                create_kwargs.pop("response_format", None)
                messages.insert(0, {
                    "role": "system",
                    "content": (
                        "IMPORTANTE: aunque no haya schema técnico disponible, responde solo JSON válido "
                        "con la forma {\"entries\": [...]} y mínimo dos líneas contables."
                    ),
                })
                response = await self._client.chat.completions.create(**create_kwargs)
            else:
                raise
        usage = response.usage
        return {
            "content": response.choices[0].message.content or "",
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
        }
