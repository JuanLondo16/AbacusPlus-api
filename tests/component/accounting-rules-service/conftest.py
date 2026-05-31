"""
Setup para component tests de accounting-rules-service.
Requiere Postgres con pgvector. Mockea Ollama.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services" / "accounting-rules-service"))

from app.dependencies import get_embedding_service  # noqa: E402
from app.infrastructure.config.auth_dependency import get_tenant_db  # noqa: E402
from app.infrastructure.config.database import Base  # noqa: E402
from app.main import app  # noqa: E402

from tests.component.conftest import make_session_factory, make_test_engine  # noqa: E402

_engine = make_test_engine(enable_vector=True)
_SessionLocal = make_session_factory(_engine)

FAKE_EMBEDDING = [0.1] * 768


class FakeEmbeddingService:
    async def embed(self, text: str) -> list[float]:
        return FAKE_EMBEDDING


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

    def _override_embed():
        return FakeEmbeddingService()

    app.dependency_overrides[get_tenant_db] = _override_db
    app.dependency_overrides[get_embedding_service] = _override_embed
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
