"""Diagnóstico fiscal: qué difiere entre Abacus y SIIGO.

El módulo es puro —no consulta base ni API— para poder probarlo entero sin red. Los datos de
estas pruebas son los reales del cliente: el comprobante de compra declara `reteiva` y
`reteica` y nada más, y de los 38 proveedores hay seis marcados como autorretenedores.
"""

from types import SimpleNamespace

import pytest
from app.domain.services.fiscal_diagnosis import (
    CODIGO_AUTORRETENEDOR,
    RESPONSABILIDADES,
    codigos_de_abacus,
    codigos_de_siigo,
    comparar_empresa,
    comparar_tercero,
)

#: El comprobante de compra tal como lo devuelve `GET /v1/document-types?type=FC`.
_COMPROBANTE = {
    "id": 19693,
    "code": "1",
    "name": "Compra",
    "type": "FC",
    "cost_center_mandatory": True,
    "reteiva": True,
    "reteica": True,
}


def _perfil(**kwargs):
    base = {
        "agente_retencion_renta": False,
        "agente_retencion_ica": False,
        "agente_retencion_iva": False,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestCodigosDeAbacus:
    def test_lee_varios_codigos_separados_por_punto_y_coma(self):
        """Es el formato real: «O-13;O-15;O-23», tal como llega del RUT de la factura."""
        assert codigos_de_abacus("O-13;O-15;O-23") == {"O-13", "O-15", "O-23"}

    def test_admite_la_coma_como_separador(self):
        assert codigos_de_abacus("O-13,O-15") == {"O-13", "O-15"}

    def test_normaliza_espacios_y_mayusculas(self):
        assert codigos_de_abacus(" o-15 ; O-13 ") == {"O-15", "O-13"}

    def test_descarta_lo_que_no_sea_un_codigo_conocido(self):
        """Un valor desconocido no puede compararse con nada y ensuciaría el informe."""
        assert codigos_de_abacus("O-15;INVENTADO;X-99") == {"O-15"}

    @pytest.mark.parametrize("vacio", [None, "", "   ", ";;"])
    def test_un_valor_vacio_no_declara_nada(self, vacio):
        assert codigos_de_abacus(vacio) == set()

    def test_los_cinco_codigos_documentados_se_reconocen(self):
        for codigo in RESPONSABILIDADES:
            assert codigos_de_abacus(codigo) == {codigo}


class TestCodigosDeSiigo:
    def test_lee_la_estructura_que_devuelve_la_api(self):
        respuesta = [{"code": "O-15", "name": "Autorretenedor"}, {"code": "O-13"}]

        assert codigos_de_siigo(respuesta) == {"O-15", "O-13"}

    @pytest.mark.parametrize("vacio", [None, [], "no es lista", [{}], [{"code": ""}]])
    def test_una_respuesta_sin_codigos_no_declara_nada(self, vacio):
        assert codigos_de_siigo(vacio) == set()


class TestComparacionDeTerceros:
    def test_cuando_coinciden_no_hay_nada_que_corregir(self):
        d = comparar_tercero(
            "830048145", "SIIGO SAS", "R-99-PN", {"fiscal_responsibilities": [{"code": "R-99-PN"}]}
        )

        assert d.coincide
        assert not d.afecta_retencion

    def test_detecta_el_autorretenedor_que_falta_en_siigo(self):
        """El caso con consecuencia: SIIGO retendría a quien no debe."""
        d = comparar_tercero(
            "900123456",
            "PROVEEDOR SAS",
            "O-13;O-15",
            {"fiscal_responsibilities": [{"code": "O-13"}]},
        )

        assert d.faltan_en_siigo == {"O-15"}
        assert d.afecta_retencion
        assert not d.coincide

    def test_detecta_codigos_que_sobran_en_siigo(self):
        """No se presume que Abacus tenga razón: el RUT puede estar desactualizado."""
        d = comparar_tercero(
            "900123456",
            "PROVEEDOR SAS",
            "O-13",
            {"fiscal_responsibilities": [{"code": "O-13"}, {"code": "O-23"}]},
        )

        assert d.sobran_en_siigo == {"O-23"}
        assert not d.afecta_retencion, "O-23 no cambia si se retiene en la fuente"

    def test_un_tercero_que_no_existe_en_siigo_se_informa_aparte(self):
        """Su solución es crearlo, no corregir un código."""
        d = comparar_tercero("900999999", "NUEVO SAS", "O-15", None)

        assert not d.existe_en_siigo
        assert not d.coincide
        assert d.en_abacus == {"O-15"}

    def test_una_diferencia_sin_autorretenedor_no_afecta_la_retencion(self):
        d = comparar_tercero(
            "900123456", "X", "O-47", {"fiscal_responsibilities": [{"code": "R-99-PN"}]}
        )

        assert not d.coincide
        assert not d.afecta_retencion

    def test_el_codigo_del_autorretenedor_es_el_de_la_dian(self):
        assert CODIGO_AUTORRETENEDOR == "O-15"
        assert RESPONSABILIDADES[CODIGO_AUTORRETENEDOR] == "Autorretenedor"


class TestComparacionDeLaEmpresa:
    def test_lo_declarado_y_habilitado_coincide(self):
        d = comparar_empresa(
            _perfil(agente_retencion_iva=True, agente_retencion_ica=True), _COMPROBANTE
        )
        por_clave = {x.clave: x for x in d}

        assert por_clave["agente_retencion_iva"].coincide
        assert por_clave["agente_retencion_ica"].coincide

    def test_detecta_lo_declarado_en_abacus_y_deshabilitado_en_siigo(self):
        comprobante = dict(_COMPROBANTE, reteica=False)

        d = comparar_empresa(_perfil(agente_retencion_ica=True), comprobante)
        ica = next(x for x in d if x.clave == "agente_retencion_ica")

        assert not ica.coincide
        assert ica.declarada_en_abacus and not ica.habilitada_en_siigo

    def test_la_retefuente_no_tiene_soporte_en_la_api(self):
        """El hallazgo que este diagnóstico existe para hacer visible."""
        d = comparar_empresa(_perfil(agente_retencion_renta=True), _COMPROBANTE)
        renta = next(x for x in d if x.clave == "agente_retencion_renta")

        assert renta.sin_soporte_en_la_api
        assert renta.habilitada_en_siigo is None
        assert not renta.coincide, "declararla y no poder enviarla ES la discrepancia"

    def test_si_no_se_declara_la_retefuente_no_hay_discrepancia(self):
        d = comparar_empresa(_perfil(agente_retencion_renta=False), _COMPROBANTE)
        renta = next(x for x in d if x.clave == "agente_retencion_renta")

        assert renta.coincide

    def test_sin_configuracion_de_siigo_no_se_inventan_alertas(self):
        """Sin poder consultar el comprobante, no se afirma que esté deshabilitado."""
        d = comparar_empresa(_perfil(agente_retencion_iva=True), None)

        assert [x.clave for x in d] == ["agente_retencion_renta"]

    def test_sin_perfil_no_se_declara_nada(self):
        d = comparar_empresa(None, _COMPROBANTE)

        assert all(not x.declarada_en_abacus for x in d)

    def test_el_caso_real_del_cliente(self):
        """Perfil con las tres activas contra el comprobante 19693, que solo tiene dos."""
        d = comparar_empresa(
            _perfil(
                agente_retencion_renta=True, agente_retencion_ica=True, agente_retencion_iva=True
            ),
            _COMPROBANTE,
        )
        problematicas = [x.etiqueta for x in d if not x.coincide]

        assert problematicas == ["Retención en la fuente (renta)"]
