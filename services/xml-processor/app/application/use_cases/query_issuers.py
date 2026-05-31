from app.infrastructure.persistence.repositories.issuer_repository import IssuerRepository


class GetIssuerByNitUseCase:
    def __init__(self, issuer_repo: IssuerRepository):
        self._issuer_repo = issuer_repo

    def execute(self, nit: str):
        return self._issuer_repo.get_by_nit(nit)
