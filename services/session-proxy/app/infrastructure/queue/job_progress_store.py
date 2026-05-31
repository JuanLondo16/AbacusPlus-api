"""
Almacena y recupera el progreso por pasos de cada job de descarga en Redis.

Estructura del hash Redis  job_progress:{job_id}:
  track_id          str
  downloaded_done   "1" | "0"
  downloaded_at     ISO 8601 | ""
  xml_done          "1" | "0"
  xml_at            ISO 8601 | ""
  xml_status        "added" | "duplicate" | "error" | ""
  xml_document_id   int str | ""
  xml_error         str | ""
  accounting_done   "1" | "0"
  accounting_at     ISO 8601 | ""
  accounting_status "triggered" | "error" | ""
  accounting_error  str | ""
"""

import logging
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 días


class JobProgressStore:
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _key(self, job_id: str) -> str:
        return f"job_progress:{job_id}"

    async def init(self, job_id: str, track_id: str) -> None:
        """Crea el registro inicial del job con todos los pasos en pending."""
        client = await self._get_client()
        key = self._key(job_id)
        await client.hset(
            key,
            mapping={
                "track_id": track_id,
                "downloaded_done": "0",
                "downloaded_at": "",
                "xml_done": "0",
                "xml_at": "",
                "xml_status": "",
                "xml_document_id": "",
                "xml_error": "",
                "accounting_done": "0",
                "accounting_at": "",
                "accounting_status": "",
                "accounting_error": "",
            },
        )
        await client.expire(key, _TTL_SECONDS)
        logger.debug("JobProgress init — job_id=%s track_id=%s", job_id, track_id)

    async def get(self, job_id: str) -> Optional[dict]:
        client = await self._get_client()
        data = await client.hgetall(self._key(job_id))
        return data if data else None
