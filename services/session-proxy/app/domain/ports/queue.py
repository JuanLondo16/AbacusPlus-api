from abc import ABC, abstractmethod
from typing import Any, Dict


class JobQueuePort(ABC):
    @abstractmethod
    async def enqueue(self, function_name: str, **kwargs: Any) -> str:
        """Encola una tarea. Retorna el job_id."""
        ...

    @abstractmethod
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Retorna el estado actual de un job."""
        ...
