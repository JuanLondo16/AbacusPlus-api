"""
Setup para component tests de llm-service.
Mockea OpenAI, rag-service, xml-processor y accounting-rules con respx.
"""

import sys
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services" / "llm-service"))

from app.dependencies import get_openai_service  # noqa: E402
from app.infrastructure.config.auth_dependency import get_tenant_db, get_token_data  # noqa: E402
from app.infrastructure.config.database import Base  # noqa: E402
from app.main import app  # noqa: E402

from tests.component.conftest import make_session_factory, make_test_engine  # noqa: E402

_engine = make_test_engine()
_SessionLocal = make_session_factory(_engine)

FAKE_OPENAI_RESPONSE = {
    "content": '{"entries": [{"cuenta": "2205", "nombre": "Proveedores", "debito": 0, "credito": 1000000}, {"cuenta": "1110", "nombre": "Bancos", "debito": 1000000, "credito": 0}]}',
    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
}


class FakeOpenAIService:
    async def complete(self, messages, json_schema=None):
        return FAKE_OPENAI_RESPONSE


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
    app.dependency_overrides[get_openai_service] = lambda: FakeOpenAIService()

    with respx.mock(assert_all_mocked=False):  # noqa: SIM117
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()
