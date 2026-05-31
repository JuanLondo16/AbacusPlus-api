import logging
import os
import re
from typing import Any, Optional

import httpx

from app.domain.exceptions.base import ExternalAuthException, ExternalRequestException
from app.domain.ports.services import ExternalClientPort

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

    def _build_login_params(self, token: str) -> dict[str, str]:
        return {
            "pk": self._fixed_pk,
            "rk": self._fixed_rk,
            "token": token,
        }

    async def login(self, login_url: str, credentials: dict[str, Any]) -> dict[str, str]:
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
                logger.info("Cookies de infraestructura capturadas: %d", len(client.cookies))

                # Paso 2: autenticar sin seguir redirects — el segundo redirect borra
                # .AspNet.ApplicationCookie, por lo que hay que capturarla aquí antes.
                response = await client.get(login_url, params=params, follow_redirects=False)
                app_cookie = response.cookies.get(".AspNet.ApplicationCookie")
                if not app_cookie:
                    raise ExternalAuthException(
                        "Token inválido o expirado: el portal no emitió .AspNet.ApplicationCookie"
                    )
                client.cookies.set(".AspNet.ApplicationCookie", app_cookie)
                cookies: dict[str, str] = dict(client.cookies)
                logger.info(
                    "Login externo exitoso: %s — %d cookie(s) capturadas",
                    login_url,
                    len(cookies),
                )
                return cookies
        except ExternalAuthException:
            raise
        except httpx.HTTPStatusError as exc:
            raise ExternalAuthException(
                f"El portal externo retornó {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise ExternalAuthException(f"No se pudo conectar al portal externo: {exc}") from exc

    async def login_and_request(
        self,
        login_url: str,
        credentials: dict[str, Any],
        method: str,
        url: str,
        body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Autentica y hace la petición en un único AsyncClient para que las cookies
        conserven sus atributos originales (dominio, path, flags Secure/HttpOnly).
        El portal DIAN requiere form-encoding y el token CSRF como campo del body.
        """
        login_params = self._build_login_params(credentials["token"])
        base_url = login_url.split("/User/")[0]
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                # Paso 1: visitar el portal para obtener cookies de infraestructura
                await client.get(base_url)

                # Paso 2: autenticar sin seguir redirects — el segundo redirect borra
                # .AspNet.ApplicationCookie, por lo que hay que capturarla aquí antes.
                auth_response = await client.get(
                    login_url, params=login_params, follow_redirects=False
                )
                app_cookie = auth_response.cookies.get(".AspNet.ApplicationCookie")
                if not app_cookie:
                    raise ExternalAuthException(
                        "Token inválido o expirado: el portal no emitió .AspNet.ApplicationCookie"
                    )
                client.cookies.set(".AspNet.ApplicationCookie", app_cookie)

                # Paso 3: visitar la raíz autenticada para obtener un __RequestVerificationToken
                # válido para la sesión activa. El token del paso 1 queda obsoleto tras el login.
                dashboard = await client.get(base_url)
                csrf_match = re.search(
                    r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"',
                    dashboard.text,
                )
                if not csrf_match:
                    raise ExternalAuthException(
                        "No se encontró __RequestVerificationToken en la página autenticada"
                    )
                csrf_token = csrf_match.group(1)
                logger.info(
                    "Login exitoso: ApplicationCookie + CSRF token obtenidos — realizando %s %s",
                    method,
                    url,
                )

                # Paso 4: petición como form-encoded (el portal rechaza JSON en estos endpoints).
                # El token CSRF va como campo del body, no como header.
                form_data = {k: str(v) for k, v in (body or {}).items()}
                form_data["__RequestVerificationToken"] = csrf_token

                response = await client.request(
                    method=method,
                    url=url,
                    data=form_data,
                    params=params,
                    headers={"X-Requested-With": "XMLHttpRequest"},
                    follow_redirects=False,
                )

                # Si el portal retorna 302, seguimos el redirect manualmente con GET
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_url = response.headers.get("location", "")
                    if not redirect_url.startswith("http"):
                        redirect_url = f"{base_url}{redirect_url}"
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
            raise ExternalRequestException(f"Fallo la petición al portal externo: {exc}") from exc

    async def login_and_download(
        self,
        login_url: str,
        credentials: dict[str, Any],
        download_url: str,
    ) -> bytes:
        """
        Autentica y descarga contenido binario en un único AsyncClient.
        Timeout de lectura extendido a 120s para ZIPs grandes.
        """
        login_params = self._build_login_params(credentials["token"])
        base_url = login_url.split("/User/")[0]
        timeout = httpx.Timeout(self._timeout, read=120.0)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                await client.get(base_url)
                # Sin seguir redirects — el segundo redirect borra ApplicationCookie
                auth_response = await client.get(
                    login_url, params=login_params, follow_redirects=False
                )
                app_cookie = auth_response.cookies.get(".AspNet.ApplicationCookie")
                if not app_cookie:
                    raise ExternalAuthException(
                        "Token inválido o expirado: el portal no emitió .AspNet.ApplicationCookie"
                    )
                client.cookies.set(".AspNet.ApplicationCookie", app_cookie)
                logger.info("Login exitoso para descarga: %s", download_url)

                response = await client.get(download_url)
                response.raise_for_status()

                if len(response.content) == 0:
                    raise ExternalRequestException(f"Respuesta vacía al descargar {download_url}")

                logger.info("ZIP descargado: %s (%d bytes)", download_url, len(response.content))
                return response.content
        except (ExternalAuthException, ExternalRequestException):
            raise
        except httpx.HTTPStatusError as exc:
            raise ExternalRequestException(
                f"El portal retornó {exc.response.status_code} para GET {download_url}"
            ) from exc
        except httpx.RequestError as exc:
            raise ExternalRequestException(f"Falló la descarga del portal externo: {exc}") from exc

    async def login_debug(self, login_url: str, credentials: dict[str, Any]) -> dict[str, Any]:
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
        cookies: dict[str, str],
        body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
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
                timeout=self._timeout,
                cookies=cookies,
                follow_redirects=True,
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
            raise ExternalRequestException(f"Fallo la petición al portal externo: {exc}") from exc
