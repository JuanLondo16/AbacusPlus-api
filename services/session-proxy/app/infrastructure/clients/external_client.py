import logging
import os
from typing import Any, Dict, Optional

import httpx

from app.domain.ports.services import ExternalClientPort
from app.domain.exceptions.base import ExternalAuthException, ExternalRequestException

logger = logging.getLogger(__name__)


class HttpxExternalClient(ExternalClientPort):
    """
    Cliente httpx sin estado. Se crea un AsyncClient fresco por llamada para
    evitar fugas de cookies entre sesiones distintas.
    """

    def __init__(self, timeout: float = 15.0):
        self._timeout = timeout
        self._fixed_pk = os.getenv("EXTERNAL_FIXED_PK", "")
        self._fixed_rk = os.getenv("EXTERNAL_FIXED_RK", "")

    def _build_login_params(self, token: str) -> Dict[str, str]:
        return {
            "pk": self._fixed_pk,
            "rk": self._fixed_rk,
            "token": token,
        }

    async def login(
        self, login_url: str, credentials: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Autentica contra el portal externo vía GET con query params pk, rk y token.
        Captura y retorna las cookies del response como dict {nombre: valor}.
        """
        params = self._build_login_params(credentials["token"])
        base_url = login_url.split("/User/")[0]
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                # Paso 1: visitar el portal para obtener cookies de infraestructura
                # (ARRAffinity, ASP.NET_SessionId, __RequestVerificationToken)
                await client.get(base_url)
                logger.info(
                    "Cookies de infraestructura capturadas: %d", len(client.cookies)
                )

                # Paso 2: autenticar con el token para obtener .AspNet.ApplicationCookie
                response = await client.get(login_url, params=params)
                response.raise_for_status()
                cookies: Dict[str, str] = dict(client.cookies)
                logger.info(
                    "Login externo exitoso: %s — %d cookie(s) capturadas",
                    login_url,
                    len(cookies),
                )
                return cookies
        except httpx.HTTPStatusError as exc:
            raise ExternalAuthException(
                f"El portal externo retornó {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise ExternalAuthException(
                f"No se pudo conectar al portal externo: {exc}"
            ) from exc

    async def login_and_request(
        self,
        login_url: str,
        credentials: Dict[str, Any],
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Autentica y hace la petición en un único AsyncClient para que las cookies
        conserven sus atributos originales (dominio, path, flags Secure/HttpOnly).
        """
        login_params = self._build_login_params(credentials["token"])
        base_url = login_url.split("/User/")[0]
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                # Paso 1: visitar el portal para obtener cookies de infraestructura
                await client.get(base_url)

                # Paso 2: autenticar con el token
                auth_response = await client.get(login_url, params=login_params)
                auth_response.raise_for_status()

                cookies_captured = dict(client.cookies)
                if not cookies_captured:
                    raise ExternalAuthException(
                        "No se pudieron obtener cookies con el token proporcionado"
                    )
                logger.info(
                    "Login exitoso: %d cookie(s) — realizando %s %s",
                    len(cookies_captured), method, url,
                )

                # Paso 2: petición al endpoint con JSON (Content-Type: application/json)
                response = await client.request(
                    method=method,
                    url=url,
                    json=body,
                    params=params,
                    follow_redirects=False,
                )

                # Si el portal retorna 302, seguimos el redirect manualmente con GET
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_url = response.headers.get("location", "")
                    if not redirect_url.startswith("http"):
                        base = url.rsplit("/", 1)[0]
                        redirect_url = f"{base}{redirect_url}"
                    logger.info("Redirect %s → GET %s", response.status_code, redirect_url)
                    response = await client.get(redirect_url)

                response.raise_for_status()

                try:
                    response_body = response.json()
                except Exception:
                    response_body = response.text

                return {
                    "status_code": response.status_code,
                    "body": response_body,
                    "headers": dict(response.headers),
                    "request_body": body,
                }
        except ExternalAuthException:
            raise
        except httpx.HTTPStatusError as exc:
            raise ExternalRequestException(
                f"El portal retornó {exc.response.status_code} para {method} {url}"
            ) from exc
        except httpx.RequestError as exc:
            raise ExternalRequestException(
                f"Fallo la petición al portal externo: {exc}"
            ) from exc

    async def login_debug(
        self, login_url: str, credentials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """[DEBUG] Ejecuta todos los pasos del login mostrando cookies por etapa."""
        params = self._build_login_params(credentials["token"])
        base_url = login_url.split("/User/")[0]
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                # Paso 1: visita previa al portal
                pre_response = await client.get(base_url)
                cookies_step1 = dict(client.cookies)

                # Paso 2: autenticación con token
                auth_response = await client.get(login_url, params=params)
                cookies_step2 = dict(client.cookies)

                return {
                    "step1_pre_visit": {
                        "url": str(pre_response.url),
                        "status": pre_response.status_code,
                        "cookies": cookies_step1,
                        "cookie_count": len(cookies_step1),
                        "set_cookie_headers": pre_response.headers.get_list("set-cookie"),
                    },
                    "step2_auth_token": {
                        "url": str(auth_response.url),
                        "request_params": params,
                        "status": auth_response.status_code,
                        "cookies": cookies_step2,
                        "cookie_count": len(cookies_step2),
                        "set_cookie_headers": auth_response.headers.get_list("set-cookie"),
                    },
                    "total_cookies": cookies_step2,
                    "total_cookie_count": len(cookies_step2),
                }
        except httpx.RequestError as exc:
            return {"error": str(exc)}

    async def request(
        self,
        method: str,
        url: str,
        cookies: Dict[str, str],
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Reenvía una petición al portal externo inyectando las cookies de sesión.
        """
        try:
            _no_cache_headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "X-Requested-With": "XMLHttpRequest",
            }
            async with httpx.AsyncClient(
                timeout=self._timeout, cookies=cookies, follow_redirects=True,
                headers=_no_cache_headers,
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=body,
                    params=params,
                )
                response.raise_for_status()
                try:
                    response_body = response.json()
                except Exception:
                    response_body = response.text

                return {
                    "status_code": response.status_code,
                    "body": response_body,
                    "headers": dict(response.headers),
                    "request_body": body,
                }
        except httpx.HTTPStatusError as exc:
            raise ExternalRequestException(
                f"El portal retornó {exc.response.status_code} para {method} {url}"
            ) from exc
        except httpx.RequestError as exc:
            raise ExternalRequestException(
                f"Fallo la petición al portal externo: {exc}"
            ) from exc
