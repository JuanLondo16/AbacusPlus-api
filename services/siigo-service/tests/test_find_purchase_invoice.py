"""RF-06: búsqueda en SIIGO de una factura de compra que quizá ya existe.

Lo que se verifica aquí es la pregunta que desbloquea un documento atascado en
«Contabilizando»: ¿creó SIIGO la factura o no? Una respuesta equivocada en cualquiera de los
dos sentidos tiene coste real —un falso negativo invita a reenviar y duplicar un asiento; un
falso positivo cierra un documento que nunca se contabilizó—, así que la coincidencia se
prueba con datos que imitan la forma exacta de la respuesta de SIIGO.
"""

from datetime import date

import pytest
from app.application.use_cases.find_purchase_invoice import FindPurchaseInvoiceUseCase


class ClienteFalso:
    """Sustituye la llamada a SIIGO devolviendo páginas ya preparadas."""

    def __init__(self, paginas):
        self.paginas = paginas
        self.llamadas = []

    def get(self, path, params=None):
        self.llamadas.append((path, dict(params or {})))
        indice = (params or {}).get("page", 1) - 1
        if indice >= len(self.paginas):
            return {"results": [], "pagination": {"total_results": self._total()}}
        return {
            "results": self.paginas[indice],
            "pagination": {"total_results": self._total()},
        }

    def _total(self):
        return sum(len(p) for p in self.paginas)


def _factura(siigo_id, numero, prefijo="FE", nombre="FC-1-125", total=150000):
    """Imita la forma de un elemento de `GET /v1/purchases`."""
    return {
        "id": siigo_id,
        "name": nombre,
        "date": "2026-08-11",
        "total": total,
        "provider_invoice": {"prefix": prefijo, "number": numero},
    }


def _caso_de_uso(cliente, monkeypatch):
    """Caso de uso con el salto a SIIGO sustituido.

    Las credenciales y la renovación del token son responsabilidad de
    `ManageCredentialsUseCase` y ya tienen sus propias pruebas; aquí interesa la lógica de
    coincidencia, que es la que decide si un documento se cierra o se reenvía.
    """
    uc = FindPurchaseInvoiceUseCase(credentials=None)
    monkeypatch.setattr(uc, "_cliente", lambda account_key: cliente, raising=False)
    return uc


# ── Coincidencia ───────────────────────────────────────────────────────────────


def test_encuentra_la_factura_por_numero_de_factura_del_proveedor(monkeypatch):
    cliente = ClienteFalso([[_factura("abc-123", "FE1234")]])
    uc = _caso_de_uso(cliente, monkeypatch)

    resultado = uc.execute(None, "FE1234", date(2026, 8, 11))

    assert len(resultado.matches) == 1
    assert resultado.matches[0].siigo_id == "abc-123"
    assert resultado.matches[0].provider_invoice_number == "FE1234"


def test_sin_coincidencias_significa_que_siigo_no_creo_nada(monkeypatch):
    """Es el resultado que autoriza a reenviar el documento sin riesgo de duplicar."""
    uc = _caso_de_uso(ClienteFalso([[_factura("abc-123", "OTRA-999")]]), monkeypatch)

    resultado = uc.execute(None, "FE1234", date(2026, 8, 11))

    assert resultado.matches == []


def test_la_comparacion_ignora_mayusculas_y_espacios(monkeypatch):
    uc = _caso_de_uso(ClienteFalso([[_factura("abc-123", " fe1234 ")]]), monkeypatch)

    assert len(uc.execute(None, "FE1234", date(2026, 8, 11)).matches) == 1


def test_una_factura_sin_provider_invoice_no_coincide(monkeypatch):
    """Nunca debe darse por buena una factura que no identifica al documento."""
    uc = _caso_de_uso(ClienteFalso([[{"id": "abc", "name": "FC-1-1", "date": "2026-08-11"}]]), monkeypatch)

    assert uc.execute(None, "FE1234", date(2026, 8, 11)).matches == []


# ── Acotación de la consulta ───────────────────────────────────────────────────


def test_la_busqueda_se_acota_por_fecha(monkeypatch):
    """Sin acotar, un barrido del histórico agotaría el cupo de SIIGO."""
    cliente = ClienteFalso([[]])
    uc = _caso_de_uso(cliente, monkeypatch)

    resultado = uc.execute(None, "FE1234", date(2026, 8, 11))

    _, params = cliente.llamadas[0]
    assert params["created_start"] == "2026-08-09"
    assert params["created_end"] == "2026-08-13"
    assert resultado.searched_from == "2026-08-09"


def test_recorre_todas_las_paginas(monkeypatch):
    cliente = ClienteFalso([[_factura("a", "OTRA")], [_factura("b", "FE1234")]])
    uc = _caso_de_uso(cliente, monkeypatch)

    resultado = uc.execute(None, "FE1234", date(2026, 8, 11))

    assert len(cliente.llamadas) == 2
    assert resultado.matches[0].siigo_id == "b"


# ── Entrada inválida ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("numero", ["", "   ", None])
def test_sin_numero_de_factura_se_rechaza_la_busqueda(numero):
    """Devolver «no encontrada» sin haber podido buscar invitaría a duplicar el asiento."""
    uc = FindPurchaseInvoiceUseCase(credentials=None)

    with pytest.raises(ValueError):
        uc.execute(None, numero, date(2026, 8, 11))
