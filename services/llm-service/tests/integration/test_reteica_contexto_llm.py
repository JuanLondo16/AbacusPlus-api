"""RF-08 · Qué ve realmente el modelo cuando tiene que decidir una ReteICA.

Estas pruebas no ejercitan al modelo —no hay modelo: la IA está mockeada—. Ejercitan **el
contexto**, que es lo único que este sistema controla. La precisión de una sugerencia de
ReteICA no se juega en la respuesta sino en lo que se le pone delante: si el municipio, la
tabla, el perfil, el tercero, la factura y la doctrina no están en el prompt, ninguna
instrucción los va a suplir; y si la doctrina llega sin rótulo, sus cifras se convierten en
tarifas.

Se afirma sobre el JSON del prompt y sobre el prompt de sistema, que son el contrato real con
el modelo.
"""

import json

import pytest
from app.application.use_cases.suggest_retentions import SuggestRetentionsUseCase

from tests.integration.test_suggest_retentions import (
    _FakeAI,
    _FakeCatalogClient,
    _FakeDocumentClient,
    _FakeIntegrationClient,
)

_CATALOGO = [
    {"id": 11, "name": "ReteICA 9.66", "type": "ReteICA", "percentage": 9.66, "active": True},
]

_ICA_RATES = [
    {
        "municipality_code": "11001",
        "municipality_name": "Bogotá D.C.",
        "retention_concept": "servicios",
        "percentage": 9.66,
        "minimum_base_uvt": 4,
    },
    {
        "municipality_code": "11001",
        "municipality_name": "Bogotá D.C.",
        "retention_concept": "compras",
        "percentage": 11.04,
        "minimum_base_uvt": 27,
    },
]

_PERFIL = {
    "agente_retencion_renta": False,
    "agente_retencion_ica": True,
    "agente_retencion_iva": False,
    "autorretenedor_renta": False,
    "gran_contribuyente": False,
    "responsable_iva": True,
    "regimen": "ordinario",
}

_DOCUMENTO = {
    "id": 5,
    "document_type": "Factura de venta",
    "date": "2026-03-15",
    "issuer_name": "ASEO INTEGRAL SAS",
    "issuer_nit": "900555111",
    "receiver_name": "IKBO SAS",
    "receiver_nit": "901000001",
    "subtotal": 3_000_000.0,
    "total_taxes": 570_000.0,
    "total": 3_570_000.0,
    "details": [{"id": 1, "description": "Servicio de aseo de oficinas", "subtotal": 3_000_000.0}],
    "taxes": [],
}

_EMISOR = {"tipo_contribuyente": "O-48", "notes": ""}


class _RagConPrecedente:
    """Devuelve una causación CONTABILIZADA de otro municipio.

    Es el caso que importa: un precedente real, del mismo proveedor, cuya jurisdicción no es
    comparable. Copiarlo aplicaría la tarifa de otra ciudad.
    """

    def __init__(self, municipio="05001"):
        self._municipio = municipio
        self.llamadas = []

    async def search(self, query, top_k=5, only_validated=False, filters=None):
        self.llamadas.append({"only_validated": only_validated, "filters": filters or {}})
        return [
            {
                "source_id": 99,
                "siigo_id": "siigo-777",
                "similarity": 0.93,
                "content": "CAUSACIÓN CONTABILIZADA\nRetenciones practicadas:\n - ReteICA 7.00",
                "metadata": {
                    "issuer_nit": "900555111",
                    "retention_types": ["reteica"],
                    "municipality_code": self._municipio,
                },
            }
        ]


def _use_case(ai_content='{"retentions": [], "missing_information": []}', rag=None):
    ai = _FakeAI(ai_content)
    uc = SuggestRetentionsUseCase(
        ai_service=ai,
        document_client=_FakeDocumentClient(_DOCUMENTO, _EMISOR),
        integration_config_client=_FakeIntegrationClient(_CATALOGO, fiscal_profile=_PERFIL),
        rag_client=rag,
        catalog_client=_FakeCatalogClient(rates=[], ica_rates=_ICA_RATES),
    )
    return uc, ai


async def _prompt(rag=None):
    uc, ai = _use_case(rag=rag)
    await uc.execute(5)
    return json.loads(ai.prompts[0]), ai.system_prompts[0]


class TestElContextoEstructuradoDeAbacusLlegaCompleto:
    """La jerarquía empieza por los datos de Abacus; ninguno puede faltar."""

    @pytest.mark.asyncio
    async def test_la_tabla_de_reteica_llega_como_fuente_vinculante(self):
        payload, _ = await _prompt()

        tabla = payload["evidencia"]["1_tarifas_oficiales_reteica_por_municipio"]
        assert "VINCULANTE" in tabla["fuerza"]
        assert len(tabla["filas"]) == 2

    @pytest.mark.asyncio
    async def test_llega_el_municipio(self):
        payload, _ = await _prompt()

        municipios = payload["documento"]["comprador"]["municipios_donde_retiene_ica"]
        assert municipios == [{"codigo": "11001", "nombre": "Bogotá D.C."}]

    @pytest.mark.asyncio
    async def test_llega_la_actividad_economica_como_concepto_por_fila(self):
        """No hay CIIU en el sistema; la actividad viaja como `retention_concept`."""
        payload, _ = await _prompt()

        conceptos = {
            f["retention_concept"]
            for f in payload["evidencia"]["1_tarifas_oficiales_reteica_por_municipio"]["filas"]
        }
        assert conceptos == {"servicios", "compras"}

    @pytest.mark.asyncio
    async def test_llega_la_base_minima_en_uvt_y_en_pesos(self):
        payload, _ = await _prompt()

        servicios = next(
            f
            for f in payload["evidencia"]["1_tarifas_oficiales_reteica_por_municipio"]["filas"]
            if f["retention_concept"] == "servicios"
        )
        assert servicios["base_minima_uvt"] == 4
        assert servicios["base_minima_pesos"] == 4 * 52_374  # UVT del año del documento

    @pytest.mark.asyncio
    async def test_llega_el_perfil_fiscal_de_la_empresa(self):
        payload, _ = await _prompt()

        comprador = payload["documento"]["comprador"]
        assert comprador["fuente"].startswith("perfil fiscal configurado")
        assert comprador["es_agente_retencion"]["ica"] is True

    @pytest.mark.asyncio
    async def test_llega_la_informacion_fiscal_del_tercero(self):
        payload, _ = await _prompt()

        emisor = payload["documento"]["emisor"]
        assert emisor["nit"] == "900555111"
        assert emisor["tipo_contribuyente"] == "O-48"
        assert emisor["responsabilidades"], "los códigos del RUT deben llegar expandidos"

    @pytest.mark.asyncio
    async def test_llega_la_factura_con_sus_renglones(self):
        payload, _ = await _prompt()

        documento = payload["documento"]
        assert documento["subtotal"] == 3_000_000.0
        assert documento["renglones"][0]["descripcion"] == "Servicio de aseo de oficinas"


class TestElConocimientoDeSiigoEntraComoContextoYNoComoTarifa:
    @pytest.mark.asyncio
    async def test_el_bloque_conceptual_llega_rotulado_y_en_el_ultimo_escalon(self):
        payload, _ = await _prompt()

        bloque = payload["evidencia"]["5_conocimiento_conceptual_reteica"]
        assert "NO VINCULANTE" in bloque["fuerza"]
        assert "NO es fuente de tarifas" in bloque["fuerza"]
        assert "siigo.com" in bloque["fuente"]["url"]

    @pytest.mark.asyncio
    async def test_explica_jurisdiccion_actividad_y_base_minima(self):
        payload, _ = await _prompt()

        temas = {p["id"] for p in payload["evidencia"]["5_conocimiento_conceptual_reteica"]["pasajes"]}
        assert {"territorialidad", "actividad_economica", "base_minima"} <= temas

    @pytest.mark.asyncio
    async def test_ninguna_cifra_del_articulo_se_presenta_como_aplicable(self):
        """La prueba central del encargo: el 0,772 % del artículo no es una tarifa universal."""
        payload, _ = await _prompt()

        bloque = payload["evidencia"]["5_conocimiento_conceptual_reteica"]
        for pasaje in bloque["pasajes"]:
            assert "%" not in pasaje["concepto"]
            if "ejemplo_ilustrativo" in pasaje:
                assert "NO" in pasaje["ejemplo_ilustrativo"] or "Ilustra" in pasaje["ejemplo_ilustrativo"]
        assert "Ninguna cifra de este bloque es aplicable" in bloque["advertencia"]

    @pytest.mark.asyncio
    async def test_el_prompt_prohibe_usar_el_bloque_como_evidencia(self):
        _, system = await _prompt()

        assert "NUNCA es `evidence` de una sugerencia" in system
        assert "no es un impuesto adicional" not in system, "la doctrina va en el payload, no aquí"

    @pytest.mark.asyncio
    async def test_el_prompt_admite_la_conversion_a_decimal_solo_como_aritmetica(self):
        _, system = await _prompt()

        assert "0,772 % = 0,00772" in system
        assert "paso ARITMÉTICO" in system

    @pytest.mark.asyncio
    async def test_el_prompt_prohibe_suponer_el_ciiu(self):
        _, system = await _prompt()

        assert "El sistema NO dispone del código" in system
        assert "no lo supongas" in system


class TestLosContabilizadosSonEvidencia:
    @pytest.mark.asyncio
    async def test_solo_se_consultan_causaciones_contabilizadas(self):
        rag = _RagConPrecedente()
        uc, _ = _use_case(rag=rag)

        await uc.execute(5)

        assert rag.llamadas[0]["only_validated"] is True

    @pytest.mark.asyncio
    async def test_el_precedente_llega_como_precedente_y_no_como_norma(self):
        payload, _ = await _prompt(rag=_RagConPrecedente())

        seccion = payload["evidencia"]["4_casos_contabilizados_similares"]
        assert "NO es norma" in seccion["fuerza"]
        assert seccion["casos"][0]["comprobante_siigo"] == "siigo-777"

    @pytest.mark.asyncio
    async def test_un_precedente_de_otro_municipio_llega_marcado_como_no_comparable(self):
        payload, _ = await _prompt(rag=_RagConPrecedente(municipio="05001"))

        caso = payload["evidencia"]["4_casos_contabilizados_similares"]["casos"][0]
        assert caso["comparabilidad"]["municipio_comparable"] is False

    @pytest.mark.asyncio
    async def test_el_prompt_prohibe_copiar_la_retencion_anterior(self):
        _, system = await _prompt(rag=_RagConPrecedente())

        assert "NUNCA copies la retención de un precedente" in system

    @pytest.mark.asyncio
    async def test_los_precedentes_consultados_quedan_en_la_trazabilidad(self):
        uc, _ = _use_case(rag=_RagConPrecedente())

        result = await uc.execute(5)

        casos = result["evidence_used"]["casos_historicos"]
        assert casos[0]["comprobante_siigo"] == "siigo-777"
        assert result["evidence_used"]["conocimiento_conceptual"]


class TestNoSeInventanTarifas:
    @pytest.mark.asyncio
    async def test_una_tarifa_del_articulo_no_pasa_la_validacion(self):
        """El modelo propone la ReteICA; el porcentaje sale del catálogo, no de su respuesta.

        Y si el catálogo trajera una tarifa que la tabla no respalda, la validación
        determinística la descarta. Aquí el 9,66 sí está en la tabla: la sugerencia procede y
        el valor se calcula por mil, que es como el municipio publica el ICA.
        """
        uc, _ = _use_case(ai_content=json.dumps(
            {"retentions": [{"tax_id": 11, "percentage": 0.772, "reason": "Servicios de aseo"}]}
        ))

        suggestion = (await uc.execute(5))["suggestions"][0]

        assert suggestion["percentage"] == 9.66  # el del catálogo, no el 0,772 del artículo
        assert suggestion["value"] == round(3_000_000 * 9.66 / 1000, 2)

    @pytest.mark.asyncio
    async def test_sin_tabla_de_reteica_no_se_propone_nada(self):
        uc = SuggestRetentionsUseCase(
            ai_service=_FakeAI(json.dumps({"retentions": [{"tax_id": 11}]})),
            document_client=_FakeDocumentClient(_DOCUMENTO, _EMISOR),
            integration_config_client=_FakeIntegrationClient(_CATALOGO, fiscal_profile=_PERFIL),
            rag_client=None,
            catalog_client=_FakeCatalogClient(rates=[], ica_rates=[]),
        )

        result = await uc.execute(5)

        assert result["suggestions"] == []
        assert any("tarifas oficiales" in w for w in result["warnings"])


class TestElContextoEsDeterminista:
    @pytest.mark.asyncio
    async def test_el_mismo_documento_produce_el_mismo_prompt(self):
        """RF-08 exige determinismo. Un corpus recuperado por orden inestable lo rompería."""
        primero, _ = await _prompt()
        segundo, _ = await _prompt()

        assert json.dumps(primero, sort_keys=False) == json.dumps(segundo, sort_keys=False)
