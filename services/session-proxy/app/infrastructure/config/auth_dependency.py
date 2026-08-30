from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.infrastructure.config.jwt_validator import decode_token

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


#: Roles que pueden alterar la configuración o la contabilidad del cliente.
#:
#: El sistema define tres roles (`tenant_admin`, `operator`, `viewer`) y hasta ahora este
#: servicio no comprobaba ninguno: bastaba estar autenticado. Un usuario invitado como «solo
#: lectura» podía escribir igual que un administrador.
#:
#: `viewer` queda deliberadamente fuera: es el único rol cuyo nombre promete una limitación, y
#: quien invita a alguien con él da por hecho que no podrá alterar nada.
ROLES_ESCRITURA = frozenset({"tenant_admin", "operator"})


def require_roles(*permitidos: str):
    """Dependencia que exige al usuario alguno de los roles indicados.

    Se aplica solo a los endpoints que escriben. Las lecturas siguen abiertas a cualquier
    usuario autenticado del cliente, que es lo que `viewer` significa.

    Un token sin ningún rol se rechaza: todos los usuarios reciben uno al crearse, así que la
    ausencia de rol no es un caso legítimo sino un token manipulado o un usuario en estado
    inconsistente. Denegar es la única respuesta segura.
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


#: Atajo para el caso mayoritario: escribir.
require_write = require_roles(*ROLES_ESCRITURA)
