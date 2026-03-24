from fastapi import APIRouter, Depends

from app.application.dto.proxy import ProxyRequest, ProxyResponse
from app.application.use_cases.proxy_request import ProxyRequestUseCase
from app.dependencies import get_proxy_request_use_case

router = APIRouter()


@router.post("/proxy/request", response_model=ProxyResponse)
async def proxy_request(
    request: ProxyRequest,
    use_case: ProxyRequestUseCase = Depends(get_proxy_request_use_case),
):
    """Reenvía una petición al portal externo usando las cookies de la sesión almacenada."""
    return await use_case.execute(request)
