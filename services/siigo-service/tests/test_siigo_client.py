"""Lógica del cliente SIIGO que no depende de la red.

Cubre la extracción de resultados según las variantes de forma que devuelve SIIGO, el cálculo
de expiración del token, la construcción de cabeceras y la terminación de la paginación. La red
(`httpx`) no se ejerce: `get_paginated` se prueba sustituyendo `get` por respuestas prefabricadas.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.infrastructure.siigo.siigo_client import (
    SiigoApiClient,
    token_expiration_from_response,
)


def _credential(**overrides):
    base = {
        "base_url": "https://api.siigo.com/",
        "username": "user@x.com",
        "access_key": "key",
        "partner_id": None,
        "access_token": None,
        "token_type": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# --- _extract_results -----------------------------------------------------------------

def test_extract_results_desde_value_results():
    payload = {"value": {"results": [{"id": 1}, {"id": 2}]}}
    assert SiigoApiClient._extract_results(payload) == [{"id": 1}, {"id": 2}]


def test_extract_results_desde_results_top_level():
    payload = {"results": [{"id": 9}]}
    assert SiigoApiClient._extract_results(payload) == [{"id": 9}]


@pytest.mark.parametrize("payload", [{}, {"value": {}}, {"results": None}, {"value": None}])
def test_extract_results_vacio(payload):
    assert SiigoApiClient._extract_results(payload) == []


# --- token_expiration_from_response ---------------------------------------------------

def test_token_expiration_usa_expires_in():
    before = datetime.now(timezone.utc)
    exp = token_expiration_from_response({"expires_in": 3600})
    delta = (exp - before).total_seconds()
    assert 3590 <= delta <= 3610


def test_token_expiration_default_cuando_falta():
    before = datetime.now(timezone.utc)
    exp = token_expiration_from_response({})
    delta = (exp - before).total_seconds()
    assert 86390 <= delta <= 86410  # default 86400 s


# --- _base_headers --------------------------------------------------------------------

def test_base_headers_sin_auth_ni_partner():
    client = SiigoApiClient(_credential())
    headers = client._base_headers(include_auth=False)
    assert headers == {"Content-Type": "application/json"}


def test_base_headers_incluye_partner_y_token():
    client = SiigoApiClient(
        _credential(partner_id="abacus", access_token="tok", token_type=None)
    )
    headers = client._base_headers()
    assert headers["Partner-Id"] == "abacus"
    assert headers["Authorization"] == "Bearer tok"  # token_type None → Bearer por defecto


def test_base_headers_respeta_token_type():
    client = SiigoApiClient(_credential(access_token="tok", token_type="MAC"))
    assert client._base_headers()["Authorization"] == "MAC tok"


def test_base_url_normaliza_trailing_slash():
    client = SiigoApiClient(_credential(base_url="https://api.siigo.com/"))
    assert client.base_url == "https://api.siigo.com"


# --- get_paginated --------------------------------------------------------------------

def test_get_paginated_recorre_todas_las_paginas():
    client = SiigoApiClient(_credential())
    paginas = [
        {"results": [{"id": 1}, {"id": 2}], "pagination": {"total_results": 3}},
        {"results": [{"id": 3}], "pagination": {"total_results": 3}},
    ]
    llamadas = {"n": 0}

    def fake_get(path, params=None):
        page = params["page"]
        llamadas["n"] += 1
        return paginas[page - 1]

    client.get = fake_get  # sustituye la llamada de red
    resultados = client.get_paginated("v1/accounts", page_size=2)
    assert [r["id"] for r in resultados] == [1, 2, 3]
    assert llamadas["n"] == 2  # paró al alcanzar total_results


def test_get_paginated_para_en_pagina_vacia():
    client = SiigoApiClient(_credential())

    def fake_get(path, params=None):
        return {"results": []}  # sin resultados ni total → debe parar

    client.get = fake_get
    assert client.get_paginated("v1/accounts") == []
