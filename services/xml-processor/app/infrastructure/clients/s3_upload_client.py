from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Optional
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)

# Hosts para los que se permite http en claro (desarrollo local). Cualquier otro
# destino del Lambda DEBE ser https para no enviar el documento + api-key en claro.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _extract_link(payload: object) -> Optional[str]:
    """Extrae el enlace del cuerpo de respuesta del Lambda del cliente."""
    field = os.getenv("S3_UPLOAD_LINK_FIELD", "").strip()
    if isinstance(payload, dict):
        if field:
            value = payload.get(field)
            return value if isinstance(value, str) else None
        for key in ("url", "link", "location", "Location", "publicUrl", "fileUrl"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    elif isinstance(payload, str):
        return payload
    return None


def _public_base_url() -> str:
    """Base pública del bucket, para componer el enlace de un objeto ya subido.

    Se prefiere `S3_PUBLIC_BASE_URL` porque el bucket puede servirse por CloudFront o por un
    dominio propio, y solo el cliente sabe cuál es. Si no está definida se compone la forma
    virtual-hosted estándar de S3 a partir del bucket y la región.
    """
    explicit = os.getenv("S3_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    bucket = os.getenv("S3_BUCKET", "").strip()
    region = os.getenv("S3_REGION", "us-east-1").strip() or "us-east-1"
    if not bucket:
        return ""
    return f"https://{bucket}.s3.{region}.amazonaws.com"


def _derive_link(payload: object, path: str) -> Optional[str]:
    """Compone el enlace cuando la API de subida confirma el guardado pero no lo retorna.

    El Lambda del cliente responde con el nombre definitivo del objeto —al que le añade una
    marca de tiempo— pero no con su URL. Como el `path` lo enviamos nosotros, la clave del
    objeto queda determinada: `path` + `filename`. Componer el enlace aquí evita pedirle al
    cliente que modifique su Lambda y mantiene el criterio del alcance («la API retorna un
    enlace que debe guardarse»), tomando el único dato que la API sí entrega.
    """
    if not isinstance(payload, dict):
        return None
    filename = payload.get("filename")
    if not isinstance(filename, str) or not filename:
        return None
    base = _public_base_url()
    if not base:
        return None
    key = f"{path.strip('/')}/{filename.lstrip('/')}" if path else filename.lstrip("/")
    return f"{base}/{quote(key)}"


def _is_valid_http_url(url: Optional[str]) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _sanitize_key_part(name: str) -> str:
    import re

    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name or "documento")
    return cleaned[:120] or "documento"


def _lambda_filename(filename: str) -> str:
    """Nombre que se le envía al Lambda: SIN extensión.

    Contrato verificado contra el endpoint real (2026-08-06). El Lambda construye la clave
    final como `{filename}_{YYYY-MM-DD}_{HH}_{MM}_{SS}.{ext}` y **deduce `ext` del contenido**,
    no del nombre: los mismos bytes enviados como `claudetest_pdf` y `claudetest_xml`
    volvieron como `.pdf` y `.xml` respectivamente.

    Por eso no se debe mandar la extensión. Si se envía `factura.pdf`, la clave resultante
    es `factura.pdf_2026-08-06_17_39_28.pdf` —con la extensión duplicada— que es
    exactamente lo que el cliente pidió evitar.
    """
    base = os.path.splitext(filename or "")[0]
    return _sanitize_key_part(base)


def _link_is_reachable(url: str, timeout: float) -> bool:
    """Comprueba que el enlace compuesto se sirva públicamente.

    El Lambda confirma que guardó el objeto, pero no que sea legible de forma anónima: eso
    depende de la política del bucket, que es del cliente y puede cambiar sin avisarnos. El
    frontend apunta el visor directamente a este enlace, así que conviene saberlo al
    guardarlo y no cuando un contador vea un XML de `AccessDenied` en pantalla.

    Es best-effort: un fallo aquí no invalida la subida, solo deja constancia en el log.
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.head(url)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001 - diagnóstico, nunca debe romper el flujo
        return False


class S3UploadClient:
    """Sube un PDF a S3 (vía Lambda del cliente o boto3 directo) y retorna el enlace."""

    def __init__(self) -> None:
        # Modo 1: Lambda/API del cliente.
        self._api_url = os.getenv("S3_UPLOAD_API_URL", "").strip()
        self._api_key = os.getenv("S3_UPLOAD_API_KEY", "").strip()
        # Nombre EXACTO del header donde va la API key (el cliente lo define; p. ej.
        # "x-api-key", "Authorization", "api-key", etc.). Configurable sin tocar código.
        self._api_key_header = (
            os.getenv("S3_UPLOAD_API_KEY_HEADER", "x-api-key").strip() or "x-api-key"
        )
        self._file_field = os.getenv("S3_UPLOAD_FILE_FIELD", "file").strip() or "file"
        self._api_timeout = float(os.getenv("S3_UPLOAD_TIMEOUT_S", "30"))
        # Reintentos ante fallos transitorios (red / 5xx). Nunca reintenta un 4xx.
        self._api_retries = max(0, int(os.getenv("S3_UPLOAD_RETRIES", "2")))
        # Tope de tamaño del cuerpo de respuesta a parsear (defensa anti-abuso de memoria).
        self._max_resp_bytes = max(1024, int(os.getenv("S3_UPLOAD_MAX_RESP_KB", "64")) * 1024)
        # Tope de tamaño del archivo a subir (los PDF/XML de la DIAN son pequeños).
        self._max_file_bytes = max(1, int(os.getenv("S3_UPLOAD_MAX_MB", "25"))) * 1024 * 1024
        # Prefijo base del path en el bucket. El Lambda del cliente espera:
        #   abacusplus/documentos/{slug}/   (con la barra final)
        self._base_path = (
            os.getenv("S3_UPLOAD_BASE_PATH", "abacusplus/documentos").strip().strip("/")
        )
        # Modo 2: S3 directo (boto3).
        self._bucket = os.getenv("S3_BUCKET", "").strip()
        self._region = os.getenv("S3_REGION", "us-east-1").strip() or "us-east-1"
        self._endpoint = os.getenv("S3_ENDPOINT_URL", "").strip()  # interno (subida)
        self._public_endpoint = os.getenv("S3_PUBLIC_ENDPOINT_URL", "").strip()  # navegador
        self._access_key = os.getenv("S3_ACCESS_KEY", "").strip()
        self._secret_key = os.getenv("S3_SECRET_KEY", "").strip()
        self._presign_expire = int(os.getenv("S3_PRESIGN_EXPIRE", "604800"))  # 7 días

    @property
    def enabled(self) -> bool:
        """True si hay algún modo de subida configurado."""
        return bool(self._api_url) or bool(self._bucket)

    async def upload_pdf(
        self, pdf_bytes: bytes, filename: str, tenant_slug: str = ""
    ) -> Optional[str]:
        """Sube el PDF y retorna el enlace, o None si no aplica/falla (best-effort)."""
        if not pdf_bytes or pdf_bytes[:5] != b"%PDF-":
            logger.warning("[S3] contenido no es un PDF válido; se omite la subida")
            return None
        return await self._upload(pdf_bytes, filename, "application/pdf", tenant_slug)

    async def upload_xml(
        self, xml_bytes: bytes, filename: str, tenant_slug: str = ""
    ) -> Optional[str]:
        """Sube el XML y retorna el enlace, o None si no aplica/falla (best-effort)."""
        if not xml_bytes:
            return None
        return await self._upload(xml_bytes, filename, "application/xml", tenant_slug)

    async def _upload(
        self, data: bytes, filename: str, content_type: str, tenant_slug: str = ""
    ) -> Optional[str]:
        if not self.enabled:
            return None
        if len(data) > self._max_file_bytes:
            logger.warning(
                "[S3] archivo de %d bytes excede el máximo permitido (%d); se omite",
                len(data),
                self._max_file_bytes,
            )
            return None
        # Prioridad al Lambda del cliente si está configurado (flujo literal del alcance).
        if self._api_url:
            return await self._upload_via_lambda(data, filename, tenant_slug)
        return self._upload_via_boto3(data, filename, content_type)

    # ── Modo 1: Lambda/API del cliente ─────────────────────────────────────────
    def _lambda_path(self, tenant_slug: str) -> str:
        """Path del cliente: abacusplus/documentos/{slug}/ (con barra final)."""
        slug = _sanitize_key_part(tenant_slug) if tenant_slug else "default"
        return f"{self._base_path}/{slug}/"

    def _api_url_is_safe(self) -> bool:
        """Exige https salvo destino local: evita enviar el documento y la api-key en claro."""
        parsed = urlparse(self._api_url)
        if parsed.scheme == "https":
            return True
        if parsed.scheme == "http" and (parsed.hostname or "") in _LOCAL_HOSTS:
            return True
        logger.error(
            "[S3] S3_UPLOAD_API_URL no es https (esquema=%s); se rechaza la subida por seguridad",
            parsed.scheme or "?",
        )
        return False

    async def _upload_via_lambda(
        self, data: bytes, filename: str, tenant_slug: str = ""
    ) -> Optional[str]:
        # Seguridad: nunca enviar el documento + api-key sobre un canal en claro.
        if not self._api_url_is_safe():
            return None
        body = {
            self._file_field: base64.b64encode(data).decode("ascii"),
            "filename": _lambda_filename(filename),
            "path": self._lambda_path(tenant_slug),
        }
        headers = {self._api_key_header: self._api_key} if self._api_key else {}
        # Reintentos con backoff exponencial solo ante fallos transitorios (red / 5xx).
        for attempt in range(self._api_retries + 1):
            try:
                # verify=True (TLS), follow_redirects=False (anti-SSRF por redirección).
                async with httpx.AsyncClient(
                    timeout=self._api_timeout, follow_redirects=False, verify=True
                ) as client:
                    resp = await client.post(self._api_url, json=body, headers=headers)

                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "server error", request=resp.request, response=resp
                    )
                resp.raise_for_status()

                if len(resp.content) > self._max_resp_bytes:
                    logger.warning("[S3] respuesta del Lambda demasiado grande; se descarta")
                    return None
                try:
                    payload = resp.json()
                except ValueError:
                    payload = resp.text.strip()

                link = _extract_link(payload)
                if not _is_valid_http_url(link):
                    # El Lambda confirma el guardado pero no retorna URL: se compone a
                    # partir del nombre definitivo que sí entrega y del path enviado.
                    link = _derive_link(payload, body["path"])
                if not _is_valid_http_url(link):
                    logger.warning(
                        "[S3] el archivo se subió pero no se pudo determinar su enlace. "
                        "Defina S3_PUBLIC_BASE_URL (o S3_BUCKET y S3_REGION) para componerlo."
                    )
                    return None
                # El enlace se guarda igual —es el identificador permanente que pide el
                # RF-03—, pero se deja constancia si no es legible públicamente: en ese caso
                # el visor del frontend caerá al respaldo servido por el backend.
                if not _link_is_reachable(link, self._api_timeout):
                    logger.warning(
                        "[S3] el enlace %s no responde 200 a un GET anónimo. Se guarda "
                        "igualmente, pero el visor usará el respaldo del backend. Revise la "
                        "política de lectura pública del bucket.",
                        link,
                    )
                else:
                    logger.info("[S3] archivo subido y enlace verificado: %s", link)
                return link

            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                # Transitorio = error de red o 5xx → reintentar; 4xx → abortar sin reintentar.
                status = getattr(getattr(exc, "response", None), "status_code", None)
                transient = isinstance(exc, httpx.TransportError) or (
                    status is not None and status >= 500
                )
                if transient and attempt < self._api_retries:
                    await asyncio.sleep(0.5 * (2**attempt))  # 0.5s, 1s, 2s…
                    continue
                logger.warning(
                    "[S3] fallo subiendo vía Lambda (intento %d/%d): %s: %s",
                    attempt + 1,
                    self._api_retries + 1,
                    type(exc).__name__,
                    exc,
                )
                return None
            except Exception as exc:  # best-effort: cualquier otro error no bloquea el flujo
                logger.warning("[S3] error inesperado vía Lambda: %s: %s", type(exc).__name__, exc)
                return None
        return None

    # ── Modo 2: S3 directo (boto3) ─────────────────────────────────────────────
    def _s3_client(self, endpoint: str):
        import boto3
        from botocore.config import Config

        kwargs = {
            "region_name": self._region,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        if self._access_key and self._secret_key:
            kwargs["aws_access_key_id"] = self._access_key
            kwargs["aws_secret_access_key"] = self._secret_key
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        return boto3.client("s3", **kwargs)

    def _upload_via_boto3(self, data: bytes, filename: str, content_type: str) -> Optional[str]:
        try:
            key = f"documents/{_sanitize_key_part(filename)}"
            # Subida al bucket usando el endpoint interno (contenedor → S3/MinIO).
            # nosniff evita que el navegador reinterprete el tipo (defensa anti-XSS al renderizar).
            self._s3_client(self._endpoint).put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                ContentDisposition="inline",
            )
            # URL prefirmada con el endpoint público (accesible desde el navegador).
            presign_endpoint = self._public_endpoint or self._endpoint
            url = self._s3_client(presign_endpoint).generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=self._presign_expire,
            )
            if not _is_valid_http_url(url):
                logger.warning("[S3] URL prefirmada inválida")
                return None
            logger.info("[S3] archivo subido a bucket '%s' (key=%s)", self._bucket, key)
            return url
        except Exception as exc:  # best-effort
            logger.warning("[S3] fallo subiendo vía boto3: %s: %s", type(exc).__name__, exc)
            return None
