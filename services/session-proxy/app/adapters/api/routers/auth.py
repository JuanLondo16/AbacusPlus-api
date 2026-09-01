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
from app.infrastructure.config.auth_dependency import get_token_data, require_write
from app.infrastructure.session.in_memory_store import InMemorySessionStore

router = APIRouter(dependencies=[Depends(get_token_data)])


@router.post(
    "/dian/sessions",
    dependencies=[Depends(require_write)],
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
    dependencies=[Depends(require_write)],
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
    dependencies=[Depends(require_write)],
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


# ELIMINADO — `GET /dian/sessions/{session_id}/debug`
#
# Devolvía el `cookies` completo de una sesión del portal de la DIAN. Estaba autenticado
# (el router entero exige token), pero eso no bastaba, por dos motivos:
#
# 1. **No distinguía roles.** Un `viewer` —el rol cuyo nombre promete que no puede tocar
#    nada— obtenía las credenciales con las que se opera ante la autoridad tributaria.
# 2. **El store no está acotado por empresa.** `InMemorySessionStore` indexa solo por
#    `session_id`, así que un usuario autenticado de un cliente podía leer las cookies DIAN
#    de otro con solo conocer el identificador —y ese identificador se escribe en el log en
#    claro al crear la sesión—.
#
# Se elimina en lugar de protegerse porque no lo llama nadie: ni el frontend ni ningún
# servicio. Era un endpoint `[DEBUG]` que solo servía para inspeccionar cookies durante el
# desarrollo, y ese valor no compensa mantener viva una vía de fuga de credenciales.
#
# Para diagnosticar el login de la DIAN queda `POST /dian/sessions/debug`, que sí exige
# `require_write` y solo devuelve las cookies del login que el propio llamante acaba de
# hacer con sus credenciales: no cruza la frontera entre clientes.
