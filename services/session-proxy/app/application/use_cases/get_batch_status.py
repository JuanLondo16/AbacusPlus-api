from datetime import datetime, timezone

from app.domain.ports.queue import JobQueuePort
from app.infrastructure.queue.batch_store import RedisBatchStore
from app.application.dto.documents import BatchStatusResponse


_DONE_STATUSES = {"complete", "not_found"}


class GetBatchStatusUseCase:
    def __init__(self, batch_store: RedisBatchStore, job_queue: JobQueuePort):
        self._store = batch_store
        self._queue = job_queue

    async def execute(self, batch_id: str) -> BatchStatusResponse:
        data = await self._store.get(batch_id)
        if data is None:
            return None

        started_at = datetime.fromisoformat(data["started_at"])
        total = data["total"]
        job_ids = data["job_ids"]

        completed = 0
        for job_id in job_ids:
            info = await self._queue.get_job_status(job_id)
            if info.get("status") in _DONE_STATUSES:
                completed += 1

        pending = total - completed
        pct = round((completed / total * 100) if total > 0 else 0, 1)

        now = datetime.now(timezone.utc)
        elapsed_seconds = (now - started_at.replace(tzinfo=timezone.utc)).total_seconds()
        elapsed_seconds = round(elapsed_seconds, 1)

        is_done = pending == 0 and total > 0
        total_time = elapsed_seconds if is_done else None

        return BatchStatusResponse(
            batch_id=batch_id,
            total=total,
            completed=completed,
            pending=pending,
            percent_done=pct,
            elapsed_seconds=elapsed_seconds,
            total_time_seconds=total_time,
            is_done=is_done,
            started_at=started_at.isoformat(),
        )
