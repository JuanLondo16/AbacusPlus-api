"""
Setup para component tests de odoo-service.
Mockea el cliente Odoo XML-RPC y rag-service. Base de datos real.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services" / "odoo-service"))

from app.dependencies import get_odoo_client, get_rag_client  # noqa: E402
from app.infrastructure.config.auth_dependency import get_tenant_db  # noqa: E402
from app.infrastructure.config.database import Base  # noqa: E402
from app.main import app  # noqa: E402

from tests.component.conftest import make_session_factory, make_test_engine  # noqa: E402

_engine = make_test_engine()
_SessionLocal = make_session_factory(_engine)


class FakeOdooClient:
    def get_invoices(self, *args, **kwargs):
        return []

    def get_journal_entries(self, *args, **kwargs):
        return []


class FakeRagClient:
    async def index_chunk(self, *args, **kwargs):
        return {"id": 1}


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
    def _override_db():
        yield db_session

    app.dependency_overrides[get_tenant_db] = _override_db
    app.dependency_overrides[get_odoo_client] = lambda: FakeOdooClient()
    app.dependency_overrides[get_rag_client] = lambda: FakeRagClient()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
