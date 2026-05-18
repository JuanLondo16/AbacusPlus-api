from typing import List, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.integration import IntegrationCredential


class IntegrationCredentialRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, provider: str, account_key: str) -> Optional[IntegrationCredential]:
        return (
            self.db.query(IntegrationCredential)
            .filter(
                IntegrationCredential.provider == provider,
                IntegrationCredential.account_key == account_key,
                IntegrationCredential.active.is_(True),
            )
            .one_or_none()
        )

    def list(self, provider: Optional[str] = None) -> List[IntegrationCredential]:
        query = self.db.query(IntegrationCredential)
        if provider:
            query = query.filter(IntegrationCredential.provider == provider)
        return query.order_by(IntegrationCredential.provider.asc(), IntegrationCredential.account_key.asc()).all()

    def upsert(
        self,
        provider: str,
        account_key: str,
        username: str,
        access_key: str,
        base_url: str,
        partner_id: Optional[str],
        auth_scheme: str,
        extra_config: Optional[dict] = None,
    ) -> IntegrationCredential:
        credential = self.get(provider, account_key)
        if credential is None:
            credential = IntegrationCredential(provider=provider, account_key=account_key)
            self.db.add(credential)

        credential.username = username
        credential.access_key = access_key
        credential.base_url = base_url.rstrip("/")
        credential.partner_id = partner_id
        credential.auth_scheme = auth_scheme
        credential.extra_config = extra_config or {}
        credential.active = True
        self.db.commit()
        self.db.refresh(credential)
        return credential
