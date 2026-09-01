from fastapi import APIRouter, Depends

from app.application.dto.proxy import ProxyRequest, ProxyResponse
from app.application.use_cases.proxy_request import ProxyRequestUseCase
from app.dependencies import get_proxy_request_use_case
from app.infrastructure.config.auth_dependency import get_token_data, require_write

router = APIRouter(dependencies=[Depends(get_token_data)])


@router.post(
    "/proxy/request",
    dependencies=[Depends(require_write)],
    response_model=ProxyResponse,
    summary="Reenviar petición autenticada al portal externo",
    description=(
        "Actúa como proxy hacia el portal configurado en `EXTERNAL_BASE_URL`. "
        "Recibe método, ruta relativa, parámetros y cuerpo opcional; autentica la petición "
        "con el token indicado y retorna el status, headers y body de la respuesta externa.\n\n"
        "Úsalo para operaciones puntuales contra el portal DIAN cuando no exista un endpoint "
        "especializado en el backend."
    ),
    response_description="Respuesta normalizada del portal externo.",
    responses={
        400: {"description": "Método HTTP no permitido, ruta inválida o cuerpo mal formado."},
        502: {"description": "Error de comunicación con el portal externo."},
    },
)
async def proxy_request(
    request: ProxyRequest,
    use_case: ProxyRequestUseCase = Depends(get_proxy_request_use_case),
):
    """Reenvía una petición al portal externo usando las cookies de la sesión almacenada."""
    return await use_case.execute(request)
