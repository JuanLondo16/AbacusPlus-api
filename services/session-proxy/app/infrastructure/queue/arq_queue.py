import logging
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job

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

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        pool = await self._get_pool()
        job = Job(job_id, pool)
        status = await job.status()
        if status.value == "not_found":
            return {"status": "not_found"}
        result_info = await job.info()
        result = result_info.result if result_info else None
        return {
            "status": status.value,
            "result": result,
        }
