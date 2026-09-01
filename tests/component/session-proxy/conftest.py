"""
Setup para component tests de session-proxy.
Sin base de datos — usa InMemorySessionStore. Mockea llamadas externas con respx.
Mockea get_token_data para saltarse la validación JWT.
"""

import sys
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[3] / "services" / "session-proxy"))

from app.infrastructure.config.auth_dependency import get_token_data  # noqa: E402
from app.main import app  # noqa: E402


class FakeTokenData:
    user_id = "test-user"
    tenant_id = 1
    tenant_slug = "test-tenant"
    roles = ["admin"]
    email = "test@example.com"
    raw_token = "fake-token"


@pytest.fixture()
def client():
    app.dependency_overrides[get_token_data] = lambda: FakeTokenData()
    with respx.mock(assert_all_mocked=False):  # noqa: SIM117
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()
