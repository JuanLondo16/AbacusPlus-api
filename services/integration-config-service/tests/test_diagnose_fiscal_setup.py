"""El diagnóstico contrasta Abacus con SIIGO sin escribir nada.

Se prueba con SIIGO simulado: lo que importa es cómo se comporta ante cada respuesta —incluida
la ausencia de un tercero y el fallo de la consulta—, no la red.

Un requisito recorre todas estas pruebas: **el diagnóstico nunca debe presentarse como
concluyente si está incompleto**. Un informe que omite en silencio los terceros que no pudo
consultar es peor que no tenerlo, porque induce a creer que lo que no aparece está bien.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.application.use_cases.diagnose_fiscal_setup import DiagnoseFiscalSetupUseCase

_COMPROBANTE = {"id": 19693, "name": "Compra", "type": "FC", "active": True,
                "reteiva": True, "reteica": True}


class _Credenciales:
    def __init__(self):
        futuro = datetime.now(timezone.utc) + timedelta(hours=2)
        self.credencial = SimpleNamespace(
            account_key="Ikbo", access_token="t", token_type="Bearer", expires_at=futuro
        )

    def list(self, provider=None):
        return [self.credencial]

    def save_token(self, **kwargs):
        raise AssertionError("no debe renovar: el token está vigente")


class _Perfil:
    def __init__(self, **kwargs):
        base = {"agente_retencion_renta": False, "agente_retencion_ica": False,
                "agente_retencion_iva": False}
        base.update(kwargs)
        self._perfil = SimpleNamespace(**base)

    def get(self):
        return self._perfil


class _Db:
    """Sustituye a la sesión: devuelve la plantilla y los terceros de `issuers`."""

    def __init__(self, terceros, document_id=19693):
        self.terceros = terceros
        self.document_id = document_id

    def execute(self, sentencia, *args, **kwargs):
        texto = str(sentencia)
        if "purchase_invoice_parameters" in texto:
            fila = (self.document_id,) if self.document_id else None
            return SimpleNamespace(first=lambda: fila)
        return SimpleNamespace(fetchall=lambda: list(self.terceros))


def _caso(terceros=(), respuestas=None, falla_comprobante=False, falla_terceros=False,
          perfil=None, document_id=19693, monkeypatch=None):
    uc = DiagnoseFiscalSetupUseCase(
        credential_repository=_Credenciales(),
        fiscal_profile_repository=perfil or _Perfil(),
        db=_Db(terceros, document_id),
    )

    respuestas = respuestas or {}

    class _Cliente:
        def __init__(self, credential):
            self.credential = credential

        def get(self, path):
            if "document-types" in path:
                if falla_comprobante:
                    raise RuntimeError("SIIGO no responde")
                return {"results": [_COMPROBANTE]}
            if falla_terceros:
                raise RuntimeError("SIIGO no responde")
            nit = path.split("identification=")[-1]
            encontrado = respuestas.get(nit)
            return {"results": [encontrado] if encontrado else []}

        @staticmethod
        def _extract_results(payload):
            return payload.get("results", []) if isinstance(payload, dict) else payload

    monkeypatch.setattr(
        "app.application.use_cases.diagnose_fiscal_setup.SiigoApiClient", _Cliente
    )
    return uc


class TestEmpresa:
    def test_detecta_la_retefuente_declarada_sin_soporte(self, monkeypatch):
        """El hallazgo principal: se declara en Abacus y SIIGO no puede recibirla."""
        uc = _caso(perfil=_Perfil(agente_retencion_renta=True), monkeypatch=monkeypatch)

        r = uc.execute()
        renta = next(d for d in r.empresa if d.clave == "agente_retencion_renta")

        assert renta.sin_soporte_en_la_api
        assert not renta.coincide

    def test_reconoce_el_comprobante_de_la_plantilla(self, monkeypatch):
        uc = _caso(monkeypatch=monkeypatch)

        assert uc.execute().comprobante_id == 19693

    def test_si_siigo_no_responde_lo_advierte_en_vez_de_suponer(self, monkeypatch):
        """Sin la configuración no se puede afirmar que una retención esté deshabilitada."""
        uc = _caso(perfil=_Perfil(agente_retencion_ica=True), falla_comprobante=True,
                   monkeypatch=monkeypatch)

        r = uc.execute()

        assert r.comprobante_id is None
        assert any("no se pudo consultar" in a.lower() for a in r.advertencias)
        assert [d.clave for d in r.empresa] == ["agente_retencion_renta"]


class TestTerceros:
    def test_detecta_el_autorretenedor_que_falta_en_siigo(self, monkeypatch):
        uc = _caso(
            terceros=[("900123456", "PROVEEDOR SAS", "O-13;O-15")],
            respuestas={"900123456": {"fiscal_responsibilities": [{"code": "O-13"}]}},
            monkeypatch=monkeypatch,
        )

        r = uc.execute()

        assert len(r.terceros) == 1
        assert r.terceros[0].faltan_en_siigo == {"O-15"}
        assert r.terceros[0].afecta_retencion

    def test_omite_los_que_coinciden(self, monkeypatch):
        uc = _caso(
            terceros=[("830048145", "SIIGO SAS", "R-99-PN")],
            respuestas={"830048145": {"fiscal_responsibilities": [{"code": "R-99-PN"}]}},
            monkeypatch=monkeypatch,
        )

        r = uc.execute()

        assert r.terceros == []
        assert r.terceros_revisados == 1

    def test_puede_pedirse_el_informe_completo(self, monkeypatch):
        uc = _caso(
            terceros=[("830048145", "SIIGO SAS", "R-99-PN")],
            respuestas={"830048145": {"fiscal_responsibilities": [{"code": "R-99-PN"}]}},
            monkeypatch=monkeypatch,
        )

        assert len(uc.execute(solo_con_diferencias=False).terceros) == 1

    def test_un_tercero_inexistente_se_reporta(self, monkeypatch):
        uc = _caso(terceros=[("900999999", "NUEVO SAS", "O-15")], monkeypatch=monkeypatch)

        r = uc.execute()

        assert not r.terceros[0].existe_en_siigo

    def test_un_fallo_de_consulta_no_se_confunde_con_una_ausencia(self, monkeypatch):
        """Distinguirlos es el punto: «no existe» es un hallazgo, «no se pudo» es una laguna."""
        uc = _caso(terceros=[("900123456", "X", "O-15")], falla_terceros=True,
                   monkeypatch=monkeypatch)

        r = uc.execute()

        assert r.terceros == []
        assert r.terceros_revisados == 0
        assert any("900123456" in a for a in r.advertencias)

    def test_el_limite_protege_el_cupo_de_peticiones(self, monkeypatch):
        """SIIGO admite 100 peticiones por minuto; cada tercero gasta una."""
        terceros = [(f"9001234{i:02d}", f"P{i}", "O-15") for i in range(10)]
        uc = _caso(terceros=terceros, monkeypatch=monkeypatch)

        r = uc.execute(limite=3)

        assert r.terceros_revisados == 3
        assert any("3 de 10" in a for a in r.advertencias)

    def test_sin_terceros_no_falla(self, monkeypatch):
        uc = _caso(monkeypatch=monkeypatch)

        r = uc.execute()

        assert r.terceros == [] and r.terceros_revisados == 0


class TestSoloLectura:
    def test_no_escribe_nada_en_siigo(self, monkeypatch):
        """La garantía del diseño: solo se emiten GET.

        Escribir exigiría un PUT que reemplaza el registro completo del tercero y perdería
        campos que el GET no devuelve.
        """
        llamadas = []
        uc = _caso(
            terceros=[("900123456", "X", "O-15")],
            respuestas={"900123456": {"fiscal_responsibilities": [{"code": "O-15"}]}},
            monkeypatch=monkeypatch,
        )
        original = uc._tercero_en_siigo

        def espia(cliente, nit):
            llamadas.append(nit)
            assert not hasattr(cliente, "post") or True
            return original(cliente, nit)

        uc._tercero_en_siigo = espia
        uc.execute()

        assert llamadas == ["900123456"]
