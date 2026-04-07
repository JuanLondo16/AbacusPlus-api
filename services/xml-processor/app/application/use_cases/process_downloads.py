import asyncio
import logging
from pathlib import Path

from app.application.dto.batch import EnqueueBatchResponse

logger = logging.getLogger(__name__)


class ProcessDownloadsUseCase:
    def __init__(self, downloads_dir: str, queue: asyncio.Queue):
        self._dir = Path(downloads_dir)
        self._queue = queue

    async def execute(self) -> EnqueueBatchResponse:
        if not self._dir.exists():
            logger.warning("Carpeta de descargas no existe: %s", self._dir)
            return EnqueueBatchResponse(queued=0, files=[])

        zip_files = sorted([f for f in self._dir.glob("*.zip") if f.is_file()])
        for zip_file in zip_files:
            await self._queue.put(zip_file)
            logger.info("ZIP encolado: %s", zip_file.name)

        logger.info("Total encolados: %d", len(zip_files))
        return EnqueueBatchResponse(
            queued=len(zip_files),
            files=[f.name for f in zip_files],
        )
