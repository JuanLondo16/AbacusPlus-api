"""
Almacena y recupera metadatos de batches de descarga en Redis.
Cada batch guarda: started_at, total de jobs y lista de job_ids.
"""
import json
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_BATCH_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 días


class RedisBatchStore:
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _key(self, batch_id: str) -> str:
        return f"batch:{batch_id}"

    async def save(self, batch_id: str, job_ids: list, started_at: datetime) -> None:
        client = await self._get_client()
        data = {
            "started_at": started_at.isoformat(),
            "total": len(job_ids),
            "job_ids": job_ids,
        }
        await client.set(self._key(batch_id), json.dumps(data), ex=_BATCH_TTL_SECONDS)
        logger.info("Batch %s guardado en Redis (%d jobs)", batch_id, len(job_ids))

    async def get(self, batch_id: str) -> Optional[dict]:
        client = await self._get_client()
        raw = await client.get(self._key(batch_id))
        if raw is None:
            return None
        return json.loads(raw)
