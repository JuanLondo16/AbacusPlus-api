import logging
from typing import Any, Dict

from arq import create_pool
from arq.connections import RedisSettings

from app.domain.ports.queue import JobQueuePort

logger = logging.getLogger(__name__)


class ArqJobQueue(JobQueuePort):
    def __init__(self, redis_url: str):
        self._redis_settings = RedisSettings.from_dsn(redis_url)
        self._pool = None  # lazy init

    async def _get_pool(self):
        if self._pool is None:
            self._pool = await create_pool(self._redis_settings)
        return self._pool

    async def enqueue(self, function_name: str, **kwargs: Any) -> str:
        pool = await self._get_pool()
        job = await pool.enqueue_job(function_name, **kwargs)
        logger.info("Job encolado: %s → %s", function_name, job.job_id)
        return job.job_id

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        pool = await self._get_pool()
        job = await pool.job(job_id)
        if job is None:
            return {"status": "not_found"}
        info = await job.info()
        return {
            "status": info.status.value if info else "unknown",
            "result": info.result if info else None,
        }
