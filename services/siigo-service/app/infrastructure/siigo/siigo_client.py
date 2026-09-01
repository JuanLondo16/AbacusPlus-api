import contextlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.domain.exceptions.base import (
    SiigoApiException,
    SiigoAuthenticationException,
    SiigoConnectionException,
)
from app.infrastructure.persistence.models.integration import IntegrationCredential

logger = logging.getLogger(__name__)

#: SIIGO documenta tiempos de respuesta promedio por debajo de 2 s, pero recomienda esperar
#: 120 s o más antes de cortar la conexión al crear comprobantes, porque en picos altos de
#: uso algunas transacciones tardan más. Cortar antes es peligroso en /v1/purchases: la
#: factura puede quedar creada sin que lleguemos a ver el id.
_DOCUMENT_TIMEOUT_SECONDS = 120.0


class _CacheTiposComprobante:
    """Caché en memoria del catálogo de tipos de comprobante, con vencimiento.

    Vive en memoria del proceso y no en base de datos a propósito: es una copia de algo que
    ya tiene dueño en SIIGO, y una copia persistida es una copia que alguien acabará
    tratando como fuente de verdad. Si el proceso reinicia, se vuelve a pedir y ya está.

    El TTL es corto en términos de catálogo pero largo en términos de lote: si el contador
    cambia la configuración en SIIGO, Abacus lo recoge en la siguiente franja sin que nadie
    tenga que tocar nada.
    """

    TTL_SEGUNDOS = 600

    def __init__(self) -> None:
        self._datos: dict[tuple, tuple] = {}

    def get(self, base_url: str, doc_type: str, document_id: int) -> Optional[dict]:
        entrada = self._datos.get((base_url, doc_type, int(document_id)))
        if entrada is None:
            return None
        guardado_en, valor = entrada
        if (datetime.now(timezone.utc) - guardado_en).total_seconds() > self.TTL_SEGUNDOS:
            return None
        return valor

    def put(self, base_url: str, doc_type: str, tipo: dict) -> None:
        if not isinstance(tipo, dict) or tipo.get("id") is None:
            return
        clave = (base_url, doc_type, int(tipo["id"]))
        self._datos[clave] = (datetime.now(timezone.utc), tipo)


_cache_tipos_comprobante = _CacheTiposComprobante()


class SiigoApiClient:
    def __init__(
        self,
        credential: IntegrationCredential,
        timeout: float = 30.0,
        document_timeout: float = _DOCUMENT_TIMEOUT_SECONDS,
    ):
        self.credential = credential
        self.base_url = credential.base_url.rstrip("/")
        self.timeout = timeout
        self.document_timeout = document_timeout

    def authenticate(self) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}/auth/access-token",
                json={
                    "username": self.credential.username,
                    "access_key": self.credential.access_key,
                },
                headers=self._base_headers(include_auth=False),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise SiigoAuthenticationException(
                f"SIIGO rejected credentials with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SiigoConnectionException(f"Could not authenticate against SIIGO: {exc}") from exc

        if "access_token" not in data:
            raise SiigoAuthenticationException("SIIGO auth response did not include access_token")
        return data

    def get_paginated(self, path: str, page_size: int = 100) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.get(path, params={"page": page, "page_size": page_size})
            page_results = self._extract_results(payload)
            results.extend(page_results)

            pagination = (
                payload.get("pagination") or payload.get("value", {}).get("pagination") or {}
            )
            total = int(pagination.get("total_results") or len(results))
            if not page_results or len(results) >= total:
                break
            page += 1
        return results

    def get(self, path: str, params: Optional[dict] = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = httpx.get(
                url, params=params, headers=self._base_headers(), timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise SiigoConnectionException(
                f"SIIGO returned status {exc.response.status_code} for {path}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SiigoConnectionException(f"Could not call SIIGO endpoint {path}: {exc}") from exc

        if isinstance(data, list):
            return {"results": data}
        return data

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = httpx.post(
                url, json=payload, headers=self._base_headers(), timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            body = ""
            with contextlib.suppress(Exception):
                body = exc.response.text
            raise SiigoConnectionException(
                f"SIIGO returned status {exc.response.status_code} for POST {path}: {body}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SiigoConnectionException(
                f"Could not POST to SIIGO endpoint {path}: {exc}"
            ) from exc

    def get_document_type(
        self, document_id: int, doc_type: str = "FC", refresh: bool = False
    ) -> Optional[dict]:
        """Configuración del tipo de comprobante, tal como la tiene la empresa en SIIGO.

        Es la fuente de verdad sobre si el comprobante exige centro de costo
        (`cost_center_mandatory`) y cuál usa por defecto (`cost_center_default`). Esos
        valores los cambia el contador en SIIGO cuando quiere, así que copiarlos a mano en
        la configuración de Abacus garantiza que tarde o temprano queden desfasados.

        El resultado se cachea porque el catálogo casi nunca cambia y SIIGO limita a 100
        peticiones por minuto y por empresa: sin caché, un lote de 50 documentos gastaría la
        mitad del cupo solo en releer lo mismo.
        """
        # `refresh` salta la caché de lectura pero no la de escritura. Lo necesita quien va a
        # leer `consecutive`: en un comprobante de numeración manual ese campo cambia con cada
        # documento emitido, y servirlo desde una copia de hasta diez minutos significaría
        # mandar dos veces el mismo número. El resto de campos —los de configuración— sí
        # aguantan la caché, que es lo que protege el cupo de 100 peticiones por minuto.
        if not refresh:
            cacheado = _cache_tipos_comprobante.get(self.base_url, doc_type, document_id)
            if cacheado is not None:
                return cacheado

        try:
            payload = self.get("/v1/document-types", params={"type": doc_type})
        except SiigoConnectionException:
            # No es motivo para abortar: sin catálogo se envía y SIIGO valida. Perder la
            # validación previa es peor que perder el envío.
            return None

        resultados = payload.get("results") if isinstance(payload, dict) else None
        if resultados is None and isinstance(payload, dict):
            resultados = payload.get("value") or []
        for tipo in resultados or []:
            _cache_tipos_comprobante.put(self.base_url, doc_type, tipo)

        return _cache_tipos_comprobante.get(self.base_url, doc_type, document_id)

    def post_document(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST de un comprobante conservando el código HTTP y los errores de SIIGO.

        Se añade en lugar de modificar `post()` para no alterar el comportamiento del envío
        de comprobantes contables, que ya está en uso y espera `SiigoConnectionException`.

        La distinción que aporta es la que RF-05 necesita para decidir si un envío puede
        reintentarse. Un timeout (`ReadTimeout`) se trata como NO reintentable a propósito:
        la petición pudo llegar a SIIGO y crear la factura aunque la respuesta se perdiera, y
        /v1/purchases no admite `Idempotency-Key` para protegerse de ese reenvío.

        SIIGO recomienda esperar 120 s o más antes de cortar la conexión en la creación de
        comprobantes, porque en picos de uso algunas transacciones tardan más de lo normal.
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = httpx.post(
                url,
                json=payload,
                headers=self._base_headers(),
                timeout=self.document_timeout,
            )
        except httpx.TimeoutException as exc:
            raise SiigoApiException(
                "SIIGO no respondió dentro del tiempo de espera. El comprobante pudo haberse "
                "creado: verifique en SIIGO antes de reenviar.",
                status_code=None,
                retryable=False,
            ) from exc
        except httpx.HTTPError as exc:
            raise SiigoApiException(
                f"No fue posible conectar con SIIGO: {exc}. El comprobante pudo haberse "
                "creado: verifique en SIIGO antes de reenviar.",
                status_code=None,
                retryable=False,
            ) from exc

        if response.status_code >= 400:
            errors: list = []
            message = f"SIIGO respondió {response.status_code}"
            # El cuerpo enviado, a DEBUG, cuando SIIGO lo rechaza.
            #
            # Los errores de validación de SIIGO nombran el campo pero no su valor —«Invalid
            # data type: number»—, así que sin ver el cuerpo la única vía de diagnóstico es
            # reenviar cambiando un campo cada vez, y cada intento gasta una petición del
            # cupo por minuto sobre la contabilidad real del cliente.
            #
            # Va a DEBUG y no a INFO porque son datos contables del cliente: se activa
            # cuando hace falta diagnosticar (LOG_LEVEL=DEBUG) y no queda en el registro
            # ordinario. No contiene credenciales: las cabeceras no se registran.
            logger.debug(
                "Cuerpo rechazado por SIIGO (%s) en %s: %s",
                response.status_code,
                path,
                json.dumps(payload, ensure_ascii=False, default=str)[:2000],
            )
            # Se conserva SIEMPRE lo que SIIGO haya dicho, venga en el formato que venga.
            #
            # Antes, un cuerpo que parseaba como JSON pero sin la clave `Errors` no entraba
            # por el `except` y su contenido se descartaba: al contador le llegaba «SIIGO
            # respondió 400» y a nadie le quedaba con qué diagnosticar. Perder la única
            # explicación que da el servidor es peor que mostrarla en crudo.
            detalle_crudo = (response.text or "").strip()
            try:
                body = response.json()
                errors = body.get("Errors") or [] if isinstance(body, dict) else []
                mensajes = [
                    e.get("Message", "").strip()
                    for e in errors
                    if isinstance(e, dict) and e.get("Message")
                ]
                if mensajes:
                    message = "; ".join(mensajes)
                elif detalle_crudo:
                    message = f"{message}: {detalle_crudo[:500]}"
            except Exception:  # noqa: BLE001 - cuerpo no JSON
                if detalle_crudo:
                    message = f"{message}: {detalle_crudo[:500]}"
            raise SiigoApiException(
                message,
                status_code=response.status_code,
                errors=errors,
                # Solo 429 y 503 son repetibles automáticamente: son los dos códigos en los
                # que SIIGO afirma no haber atendido la petición —cupo agotado y servicio no
                # disponible—, así que repetirla no puede duplicar nada.
                #
                # 500, 502 y 504 estaban aquí y se han retirado. Un 5xx genérico no dice en
                # qué punto se interrumpió el proceso: la factura pudo quedar creada y el
                # fallo ocurrir al responder. Repetirla automáticamente en ese caso crea un
                # segundo asiento contable real, y /v1/purchases no admite `Idempotency-Key`
                # para impedirlo. Esos códigos salen ahora por la vía de la reconciliación,
                # que verifica contra SIIGO en lugar de suponer.
                retryable=response.status_code in (429, 503),
            )

        try:
            return response.json()
        except ValueError as exc:
            raise SiigoApiException(
                "SIIGO respondió con un cuerpo que no es JSON válido. El comprobante pudo "
                "haberse creado: verifique en SIIGO antes de reenviar.",
                status_code=response.status_code,
                retryable=False,
            ) from exc

    def _base_headers(self, include_auth: bool = True) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.credential.partner_id:
            headers["Partner-Id"] = self.credential.partner_id
        if include_auth and self.credential.access_token:
            token_type = self.credential.token_type or "Bearer"
            headers["Authorization"] = f"{token_type} {self.credential.access_token}"
        return headers

    @staticmethod
    def _extract_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
        value = payload.get("value")
        if isinstance(value, dict) and isinstance(value.get("results"), list):
            return value["results"]
        if isinstance(payload.get("results"), list):
            return payload["results"]
        return []


def token_expiration_from_response(response: dict[str, Any]) -> datetime:
    expires_in = int(response.get("expires_in") or 86400)
    return datetime.now(timezone.utc) + timedelta(seconds=expires_in)
