from app.application.dto.documents import DownloadJobStatus
from app.domain.ports.queue import JobQueuePort


class GetJobStatusUseCase:
    def __init__(self, job_queue: JobQueuePort):
        self._queue = job_queue

    async def execute(self, job_id: str) -> DownloadJobStatus:
        info = await self._queue.get_job_status(job_id)
        return DownloadJobStatus(
            job_id=job_id,
            status=info.get("status", "unknown"),
            result=info.get("result"),
        )
