from fastapi import APIRouter, Depends, HTTPException, status

from app.application.dto.auth import LoginRequest, LoginResponse
from app.application.dto.company_login import CompanyLoginResponse
from app.application.use_cases.company_login import CompanyLoginUseCase
from app.application.use_cases.login import LoginUseCase
from app.dependencies import (
    get_company_login_use_case,
    get_external_client,
    get_login_use_case,
    get_session_store,
)
from app.domain.exceptions.base import BrowserLoginException
from app.infrastructure.clients.external_client import HttpxExternalClient
from app.infrastructure.config.auth_dependency import get_token_data
from app.infrastructure.session.in_memory_store import InMemorySessionStore

router = APIRouter(dependencies=[Depends(get_token_data)])


@router.post(
    "/dian/sessions",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear sesión DIAN con token",
    description=(
        "Autentica contra el portal externo configurado con `EXTERNAL_BASE_URL` y "
        "`EXTERNAL_LOGIN_PATH` usando el token recibido en el cuerpo de la petición.\n\n"
        "Si la autenticación es exitosa, captura las cookies retornadas por el portal "
        "y crea una sesión local identificada por `session_id` para reutilizarla en "
        "peticiones posteriores."
    ),
    response_description="Sesión creada con su identificador local.",
    responses={
        400: {"description": "Token inválido o petición mal formada."},
        502: {"description": "No fue posible autenticar contra el portal externo."},
    },
)
async def login(
    request: LoginRequest,
    use_case: LoginUseCase = Depends(get_login_use_case),
):
    """Autentica con el portal externo, captura cookies y crea una sesión. Retorna session_id."""
    return await use_case.execute(request)


@router.delete(
    "/dian/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión DIAN local",
    description=(
        "Elimina del store local la sesión asociada al `session_id` recibido. "
        "La operación es idempotente: si la sesión no existe o ya expiró, responde igualmente `204`."
    ),
    response_description="Sesión eliminada o ya inexistente.",
)
async def logout(
    session_id: str,
    store: InMemorySessionStore = Depends(get_session_store),
):
    """Elimina la sesión del store. Idempotente — sin error si el session_id no existe."""
    store.delete(session_id)


@router.post(
    "/dian/sessions/debug",
    summary="[DEBUG] Probar login DIAN y ver cookies",
    description=(
        "Endpoint de diagnóstico para ejecutar el login contra el portal externo y "
        "retornar detalles de la petición junto con las cookies capturadas.\n\n"
        "Está pensado para pruebas de integración/configuración; no crea una sesión "
        "operativa para el flujo normal."
    ),
    response_description="Datos de depuración del login y cookies retornadas por el portal.",
    responses={
        400: {"description": "Token inválido o petición mal formada."},
        502: {"description": "Error de comunicación con el portal externo."},
    },
)
async def login_debug(
    request: LoginRequest,
    client: HttpxExternalClient = Depends(get_external_client),
) -> dict:
    """[DEBUG] Ejecuta el login y retorna cookies capturadas + URL y parámetros enviados."""
    import os

    login_url = os.getenv("EXTERNAL_BASE_URL", "").rstrip("/") + os.getenv(
        "EXTERNAL_LOGIN_PATH", ""
    )
    return await client.login_debug(
        login_url=login_url,
        credentials={"token": request.token},
    )


@router.post(
    "/dian/sessions/company",
    response_model=CompanyLoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear sesión DIAN mediante formulario de empresa",
    description=(
        "Abre un navegador automatizado, completa el formulario de CompanyLogin del portal DIAN "
        "con los datos configurados por variables de entorno y captura las cookies resultantes.\n\n"
        "Usa este endpoint cuando el portal requiere flujo interactivo de compañía en vez de "
        "autenticación directa por token."
    ),
    response_description="Sesión creada desde el flujo de login de compañía.",
    responses={
        502: {
            "description": "El navegador no pudo completar el login o el portal rechazó la autenticación."
        },
    },
)
async def company_login(
    use_case: CompanyLoginUseCase = Depends(get_company_login_use_case),
):
    """Abre browser, completa formulario DIAN CompanyLogin y retorna session_id."""
    try:
        return await use_case.execute()
    except BrowserLoginException as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": e.message, "steps": e.steps},
        )


@router.get(
    "/dian/sessions/{session_id}/debug",
    summary="[DEBUG] Ver sesión DIAN almacenada",
    description=(
        "Retorna las cookies y metadatos de una sesión almacenada en memoria. "
        "Sirve para verificar expiración, cantidad de cookies y tiempos de acceso durante pruebas."
    ),
    response_description="Información de depuración de la sesión local.",
    responses={
        404: {"description": "Sesión no encontrada o expirada."},
    },
)
async def debug_session(
    session_id: str,
    store: InMemorySessionStore = Depends(get_session_store),
) -> dict:
    """[DEBUG] Retorna las cookies e información de la sesión almacenada."""
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o expirada")
    return {
        "session_id": session.session_id,
        "cookies": session.cookies,
        "cookie_count": len(session.cookies),
        "created_at": session.created_at.isoformat(),
        "last_accessed_at": session.last_accessed_at.isoformat(),
    }
