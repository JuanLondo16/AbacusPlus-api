from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text, UniqueConstraint, func
from app.infrastructure.config.database import Base


class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"
    __table_args__ = (
        UniqueConstraint("provider", "account_key", name="uq_integration_provider_account"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, index=True)
    account_key = Column(String(120), nullable=False, default="default")
    username = Column(String(255), nullable=True)
    access_key = Column(Text, nullable=True)
    access_token = Column(Text, nullable=True)
    token_type = Column(String(50), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    base_url = Column(String(255), nullable=False)
    partner_id = Column(String(255), nullable=True)
    auth_scheme = Column(String(50), nullable=False, default="oauth_jwt")
    extra_config = Column(JSON, nullable=False, default=dict)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
