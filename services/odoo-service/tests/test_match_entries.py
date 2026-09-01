"""Matching masivo de asientos in_invoice con documentos DIAN.

`MatchEntriesUseCase.execute()` recorre los asientos sin documento y agrega el resultado.
Se prueba la orquestación (conteos y aislamiento de errores) con un repositorio falso, sin
tocar la base de datos ni Odoo.
"""

from types import SimpleNamespace

from app.application.use_cases.match_entries import MatchEntriesUseCase


class _FakeRepo:
    """Repositorio falso: `find_and_link_document` devuelve lo que diga `resultados`.

    Cada elemento de `resultados` es un id (match), None (sin match) o una Exception
    (fallo puntual que no debe abortar el recorrido).
    """

    def __init__(self, entries, resultados):
        self._entries = entries
        self._resultados = list(resultados)
        self.llamadas = 0

    def get_unmatched_in_invoices(self):
        return self._entries

    def find_and_link_document(self, entry):
        resultado = self._resultados[self.llamadas]
        self.llamadas += 1
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


def _entries(n):
    return [SimpleNamespace(id=i, source_id=f"src-{i}") for i in range(n)]


def test_sin_asientos_devuelve_ceros():
    repo = _FakeRepo(entries=[], resultados=[])
    result = MatchEntriesUseCase(repo).execute()
    assert result == {"total_reviewed": 0, "matched": 0, "unmatched": 0, "errors": []}


def test_cuenta_matched_y_unmatched():
    repo = _FakeRepo(entries=_entries(3), resultados=[101, None, 103])
    result = MatchEntriesUseCase(repo).execute()
    assert result["total_reviewed"] == 3
    assert result["matched"] == 2
    assert result["unmatched"] == 1
    assert result["errors"] == []


def test_un_error_no_aborta_el_recorrido():
    # El 2º asiento falla; el 1º y el 3º deben procesarse igual.
    repo = _FakeRepo(entries=_entries(3), resultados=[101, RuntimeError("boom"), 103])
    result = MatchEntriesUseCase(repo).execute()
    assert repo.llamadas == 3  # se recorrieron los tres pese al error
    assert result["total_reviewed"] == 3
    assert result["matched"] == 2
    assert result["unmatched"] == 0
    assert len(result["errors"]) == 1
    assert result["errors"][0]["entry_id"] == 1
    assert result["errors"][0]["source_id"] == "src-1"
    assert "boom" in result["errors"][0]["error"]
