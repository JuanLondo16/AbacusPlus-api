from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.infrastructure.config.jwt_validator import decode_token
from app.infrastructure.config.tenant_connection_manager import get_session_for_tenant

_bearer = HTTPBearer()


class TokenData:
    def __init__(self, payload: dict, raw_token: str):
        self.user_id = payload["sub"]
        self.tenant_id = payload["tenant_id"]
        self.tenant_slug = payload["tenant_slug"]
        self.roles: list[str] = payload.get("roles", [])
        self.email: str = payload.get("email", "")
        self.raw_token = raw_token


def get_token_data(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> TokenData:
    try:
        payload = decode_token(credentials.credentials)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    return TokenData(payload, credentials.credentials)


#: Roles que pueden lanzar asignaciones de cuenta (RF-04), pedir sugerencias de retención
#: (RF-08) o alterar los prompts que gobiernan ambas.
#:
#: Se replica aquí en lugar de compartirse porque los servicios de este proyecto no comparten
#: código por diseño; la definición debe mantenerse en sintonía con la del xml-processor.
ROLES_ESCRITURA = frozenset({"tenant_admin", "operator"})


def require_roles(*permitidos: str):
    """Dependencia que exige al usuario alguno de los roles indicados.

    Un token sin ningún rol se rechaza: todos los usuarios reciben uno al crearse, así que su
    ausencia no es un caso legítimo sino un token manipulado o un usuario inconsistente.
    """
    permitidos_set = frozenset(permitidos)

    def _verificar(token: Annotated[TokenData, Depends(get_token_data)]) -> TokenData:
        if not permitidos_set.intersection(token.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Su usuario no tiene permiso para esta operación. "
                    f"Se requiere uno de estos roles: {', '.join(sorted(permitidos_set))}."
                ),
            )
        return token

    return _verificar


require_write = require_roles(*ROLES_ESCRITURA)


def get_tenant_db(token: Annotated[TokenData, Depends(get_token_data)]):
    db = get_session_for_tenant(token.tenant_slug)
    try:
        yield db
    finally:
        db.close()
