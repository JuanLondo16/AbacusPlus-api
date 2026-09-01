"""RF-08 · Criterios de retención del contador: lectura y reemplazo."""

from app.application.dto.retention_criteria import (
    RetentionCriteriaReplaceRequest,
    RetentionCriteriaResponse,
    RetentionCriterionItem,
)
from app.infrastructure.persistence.repositories.retention_criteria_repository import (
    RetentionCriteriaRepository,
)


class ManageRetentionCriteriaUseCase:
    def __init__(self, repo: RetentionCriteriaRepository):
        self._repo = repo

    def get(self, only_active: bool = True) -> RetentionCriteriaResponse:
        """Criterios vigentes del tenant. Lista vacía si aún no tiene ninguno.

        La ausencia no es un error: un tenant sin criterios simplemente aporta una fuente
        menos al prompt, y la sugerencia se apoya en las tablas oficiales y el perfil fiscal,
        que son las fuentes vinculantes.
        """
        filas = self._repo.list_all(only_active=only_active)
        criterios = [RetentionCriterionItem.model_validate(f) for f in filas]
        return RetentionCriteriaResponse(criterios=criterios, total=len(criterios))

    def replace(self, request: RetentionCriteriaReplaceRequest) -> RetentionCriteriaResponse:
        filas = self._repo.replace_all([c.model_dump() for c in request.criterios])
        criterios = [RetentionCriterionItem.model_validate(f) for f in filas]
        return RetentionCriteriaResponse(criterios=criterios, total=len(criterios))
