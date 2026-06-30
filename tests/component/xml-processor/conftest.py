"""
Setup para component tests de xml-processor.
Mockea rag-service y llm-service con respx.
Base de datos real con SQLAlchemy.
"""

import sys
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services" / "xml-processor"))

from app.dependencies import (  # noqa: E402
    get_llm_client,
    get_rag_client,
)
from app.infrastructure.config.auth_dependency import get_tenant_db, get_token_data  # noqa: E402
from app.infrastructure.config.database import Base  # noqa: E402
from app.main import app  # noqa: E402

from tests.component.conftest import make_session_factory, make_test_engine  # noqa: E402

_engine = make_test_engine()
_SessionLocal = make_session_factory(_engine)


class FakeRagClient:
    async def index_chunk(self, *args, **kwargs):
        return {"id": 1}


class FakeLlmClient:
    async def generate_accounting_entry(self, *args, **kwargs):
        return {"entries": []}

    async def get_document_with_accounting(self, *args, **kwargs):
        return None


class FakeTokenData:
    user_id = "test-user"
    tenant_id = 1
    tenant_slug = "test-tenant"
    roles = ["admin"]
    email = "test@example.com"
    raw_token = "fake-token"


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
    app.dependency_overrides[get_token_data] = lambda: FakeTokenData()
    app.dependency_overrides[get_rag_client] = lambda: FakeRagClient()
    app.dependency_overrides[get_llm_client] = lambda: FakeLlmClient()

    with respx.mock(assert_all_mocked=False):  # noqa: SIM117
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()
