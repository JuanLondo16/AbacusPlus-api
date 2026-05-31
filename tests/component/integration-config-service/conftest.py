"""
Setup para component tests de integration-config-service.
No tiene dependencias externas HTTP — solo base de datos.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services" / "integration-config-service"))

from app.infrastructure.config.auth_dependency import get_tenant_db  # noqa: E402
from app.infrastructure.config.database import Base  # noqa: E402
from app.main import app  # noqa: E402

from tests.component.conftest import make_session_factory, make_test_engine  # noqa: E402

_engine = make_test_engine()
_SessionLocal = make_session_factory(_engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def db_session():
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture()
def client(db_session: Session):
    def _override():
        yield db_session

    app.dependency_overrides[get_tenant_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
