from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.dto.auth import LoginRequest, LoginResponse
from app.application.use_cases.login import LoginUseCase
from app.infrastructure.session.in_memory_store import InMemorySessionStore
from app.infrastructure.clients.external_client import HttpxExternalClient
from app.dependencies import get_login_use_case, get_session_store, get_external_client

router = APIRouter()


@router.post("/dian/auth", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def login(
    request: LoginRequest,
    use_case: LoginUseCase = Depends(get_login_use_case),
):
    """Autentica con el portal externo, captura cookies y crea una sesión. Retorna session_id."""
    return await use_case.execute(request)


@router.delete("/dian/logout/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session_id: str,
    store: InMemorySessionStore = Depends(get_session_store),
):
    """Elimina la sesión del store. Idempotente — sin error si el session_id no existe."""
    store.delete(session_id)


@router.post("/dian/auth/debug")
async def login_debug(
    request: LoginRequest,
    client: HttpxExternalClient = Depends(get_external_client),
) -> Dict:
    """[DEBUG] Ejecuta el login y retorna cookies capturadas + URL y parámetros enviados."""
    import os
    login_url = os.getenv("EXTERNAL_BASE_URL", "").rstrip("/") + os.getenv("EXTERNAL_LOGIN_PATH", "")
    return await client.login_debug(
        login_url=login_url,
        credentials={"token": request.token},
    )


@router.get("/dian/debug/{session_id}")
async def debug_session(
    session_id: str,
    store: InMemorySessionStore = Depends(get_session_store),
) -> Dict:
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
