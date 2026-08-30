from typing import Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.tenant_fiscal_profile import TenantFiscalProfile

# Fila única del perfil por base de tenant.
_SINGLETON_ID = 1


class TenantFiscalProfileRepository:
    def __init__(self, db: Session):
        self._db = db

    def get(self) -> Optional[TenantFiscalProfile]:
        return self._db.get(TenantFiscalProfile, _SINGLETON_ID)

    def upsert(self, values: dict) -> TenantFiscalProfile:
        """Crea la fila única o actualiza la existente. Un solo registro por tenant."""
        profile = self._db.get(TenantFiscalProfile, _SINGLETON_ID)
        if profile is None:
            profile = TenantFiscalProfile(id=_SINGLETON_ID, **values)
            self._db.add(profile)
        else:
            for key, value in values.items():
                setattr(profile, key, value)
        self._db.commit()
        self._db.refresh(profile)
        return profile
