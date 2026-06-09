from typing import Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.tenant import Tenant


class TenantRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_by_slug(self, slug: str) -> Optional[Tenant]:
        return self._db.query(Tenant).filter(Tenant.slug == slug, Tenant.is_active == True).first()

    def get_by_email_domain(self, domain: str) -> Optional[Tenant]:
        return (
            self._db.query(Tenant)
            .filter(Tenant.email_domain == domain, Tenant.is_active == True)
            .first()
        )

    def get_by_id(self, tenant_id) -> Optional[Tenant]:
        return self._db.query(Tenant).filter(Tenant.id == tenant_id).first()

    def list_all(self) -> list[Tenant]:
        return (
            self._db.query(Tenant)
            .filter(Tenant.is_active == True)
            .order_by(Tenant.created_at)
            .all()
        )

    def create(self, slug: str, display_name: str, email_domain: Optional[str] = None) -> Tenant:
        tenant = Tenant(slug=slug, display_name=display_name, email_domain=email_domain)
        self._db.add(tenant)
        self._db.commit()
        self._db.refresh(tenant)
        return tenant
