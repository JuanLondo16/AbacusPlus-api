"""
Setup para component tests de siigo-service.
Mockea el API de SIIGO con respx. Base de datos real.
"""

import sys
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# El conftest compartido se importa ANTES de anadir el servicio al sys.path: cada
# services/<svc>/tests es un paquete regular (tiene __init__.py) y, en Python, un
# paquete regular gana siempre sobre el namespace package de la raiz, sin importar
# el orden de sys.path. Importarlo primero lo deja resuelto en sys.modules.
from tests.component.conftest import make_session_factory, make_test_engine  # noqa: E402

sys.path.append(str(Path(__file__).resolve().parents[3] / "services" / "siigo-service"))

from app.infrastructure.config.auth_dependency import get_tenant_db  # noqa: E402
from app.infrastructure.config.database import Base  # noqa: E402
from app.main import app  # noqa: E402

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
    def _override_db():
        yield db_session

    app.dependency_overrides[get_tenant_db] = _override_db
    with respx.mock(assert_all_mocked=False):  # noqa: SIM117
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()
