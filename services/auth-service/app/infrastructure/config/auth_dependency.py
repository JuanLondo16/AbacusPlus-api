"""Autenticación y autorización de los endpoints administrativos del auth-service.

Hasta ahora este servicio era el único sin ninguna comprobación: `POST /api/v1/users/invite`,
`GET /api/v1/users` y `GET|POST /api/v1/tenants` resolvían el cliente a partir del header
`X-Tenant-Slug` que enviaba quien llamara, sin exigir token. Como el gateway enruta esas
rutas hacia afuera, cualquiera en la red podía listar los usuarios de cualquier cliente y —lo
grave— crear un usuario con rol `tenant_admin` dentro de él y entrar como administrador.

Las dos piezas que lo cierran:

* **El cliente se toma del token, nunca del header.** El header sigue existiendo porque Nginx
  lo inyecta desde el subdominio, pero ya no decide sobre qué base se escribe. Si el token
  dice `ikbo`, se opera sobre `ikbo` aunque el header diga otra cosa.
* **Administrar usuarios exige `tenant_admin`.** Invitar es la operación que reparte
  privilegios; dejarla a un `operator` o a un `viewer` haría inútil la separación de roles que
  el resto del sistema ya respeta.
"""

import hmac
import os
from typing import Annotated, Optional

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.infrastructure.config.jwt import decode_token

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


def require_tenant_admin(
    token: Annotated[TokenData, Depends(get_token_data)],
) -> TokenData:
    """Exige `tenant_admin`: administrar usuarios es repartir privilegios."""
    if "tenant_admin" not in token.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador del cliente puede administrar usuarios.",
        )
    return token


def require_bootstrap_secret(
    # El header se declara opcional a propósito. Si fuera obligatorio, FastAPI respondería 422
    # («falta un campo») antes de ejecutar esta función, y omitir el secreto daría un código
    # distinto que enviarlo mal. Ambos casos son lo mismo —no estás autorizado— y deben
    # responder 403, sin pistas sobre qué header espera el servidor.
    x_internal_secret: Optional[str] = Header(
        None,
        alias="X-Internal-Secret",
        description="Secreto compartido entre servicios. Requerido para provisionar clientes.",
    ),
) -> None:
    """Protege el alta de clientes, que por definición no puede exigir un usuario previo.

    `POST /api/v1/tenants` crea una base de datos y llama a los ocho servicios para montar sus
    tablas: es la operación más cara del sistema y la única que no tiene detrás a nadie
    autenticado, porque el primer administrador nace precisamente de ella. Sin ninguna barrera,
    cualquiera podía provocar la creación indefinida de bases de datos.

    Se reutiliza `INTERNAL_SECRET` —ya presente en todos los contenedores— en vez de introducir
    otra variable: es el mismo secreto que ya autoriza las rutas `/internal/` que este endpoint
    invoca a continuación, así que quien puede provisionar ya lo tenía.

    Si la variable no está definida se deniega. Fallar cerrado es lo correcto aquí: un
    despliegue mal configurado no debe traducirse en un endpoint abierto.
    """
    expected = os.getenv("INTERNAL_SECRET")
    if not expected or not x_internal_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if not hmac.compare_digest(x_internal_secret, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
