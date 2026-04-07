"""
Worker ARQ para descarga de ZIPs del portal DIAN.

Ejecutar con:
    python -m arq app.infrastructure.workers.download_worker.WorkerSettings
"""
import logging
import os
from pathlib import Path

from arq.connections import RedisSettings

from app.infrastructure.clients.external_client import HttpxExternalClient
from app.infrastructure.config.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


async def download_zip(ctx: dict, track_id: str, token: str) -> dict:
    """
    Tarea ARQ: autentica en DIAN y descarga el ZIP para el track_id dado.
    """
    base_url = os.getenv("EXTERNAL_BASE_URL", "").rstrip("/")
    login_url = base_url + os.getenv("EXTERNAL_LOGIN_PATH", "/User/AuthToken")
    download_url = f"{base_url}/Document/DownloadZipFiles?trackId={track_id}"
    downloads_dir = Path(os.getenv("DOWNLOADS_DIR", "/app/downloads"))
    downloads_dir.mkdir(parents=True, exist_ok=True)

    client: HttpxExternalClient = ctx["external_client"]

    logger.info("Iniciando descarga ZIP — trackId: %s", track_id)
    content = await client.login_and_download(
        login_url=login_url,
        credentials={"token": token},
        download_url=download_url,
    )

    file_path = downloads_dir / f"{track_id}.zip"
    file_path.write_bytes(content)

    logger.info("ZIP guardado: %s (%d bytes)", file_path, len(content))
    return {
        "track_id": track_id,
        "file": str(file_path),
        "size_bytes": len(content),
    }


async def on_startup(ctx: dict) -> None:
    ctx["external_client"] = HttpxExternalClient(timeout=15.0)
    logger.info("Worker ARQ iniciado — cliente httpx listo")


async def on_shutdown(ctx: dict) -> None:
    logger.info("Worker ARQ apagándose")


class WorkerSettings:
    functions = [download_zip]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
    max_jobs = 5
    job_timeout = 180
    keep_result = 3600
    max_tries = 3
