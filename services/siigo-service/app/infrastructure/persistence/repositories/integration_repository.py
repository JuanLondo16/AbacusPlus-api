from datetime import datetime
from typing import Optional

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

    def upsert(
        self,
        provider: str,
        account_key: str,
        username: str,
        access_key: str,
        base_url: str,
        partner_id: Optional[str],
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
        credential.extra_config = extra_config or {}
        credential.active = True
        self.db.commit()
        self.db.refresh(credential)
        return credential

    def save_token(
        self,
        credential: IntegrationCredential,
        access_token: str,
        token_type: str,
        expires_at: datetime,
    ) -> IntegrationCredential:
        credential.access_token = access_token
        credential.token_type = token_type
        credential.expires_at = expires_at
        self.db.commit()
        self.db.refresh(credential)
        return credential
