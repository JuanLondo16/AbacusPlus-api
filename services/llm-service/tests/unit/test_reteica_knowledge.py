"""RF-08 · El conocimiento conceptual de ReteICA es contexto, nunca fuente de tarifas.

Lo que se fija aquí no es que el corpus «esté», sino que **no puede ascender**: que sus cifras
llegan al modelo marcadas como ejemplo, que el bloque va numerado por debajo de los
precedentes, que declara su procedencia y que la recuperación es determinista. Un corpus
doctrinal mal rotulado es peor que ninguno: convierte un ejemplo de un artículo divulgativo en
una tarifa que se le retiene a un tercero real.
"""

import re

import pytest
from app.application.services.retention_evidence import (
    EvidenceBundle,
    RetentionEvidenceRetriever,
)
from app.domain.knowledge import reteica_knowledge

_DOCUMENTO = {
    "issuer_name": "ASEO INTEGRAL SAS",
    "issuer_nit": "900555111",
    "details": [{"id": 1, "description": "Servicios de aseo en oficinas de Bogotá"}],
}


class TestElCorpusSeRecuperaYSeRotula:
    def test_el_nucleo_conceptual_llega_aunque_la_factura_no_lo_mencione(self):
        """Territorialidad, actividad y base mínima no pueden depender de una coincidencia.

        Son los tres conceptos cuya ausencia producía el fallo. Hacerlos depender de que la
        descripción de un renglón diga «municipio» significaría que algún día no llegan sin
        que nadie lo note.
        """
        ids = {p["id"] for p in reteica_knowledge.recuperar("Compra de papelería")}

        assert {"territorialidad", "actividad_economica", "base_minima"} <= ids

    def test_la_recuperacion_es_determinista(self):
        primera = reteica_knowledge.recuperar("Servicios de aseo en Bogotá")
        segunda = reteica_knowledge.recuperar("Servicios de aseo en Bogotá")

        assert [p["id"] for p in primera] == [p["id"] for p in segunda]

    def test_no_se_vuelca_el_corpus_entero_en_cada_prompt(self):
        pasajes = reteica_knowledge.recuperar("servicios municipio tarifa base calculo actividad")

        assert 0 < len(pasajes) <= 5

    def test_el_bloque_declara_procedencia_y_advertencia(self):
        bloque = reteica_knowledge.bloque_para_prompt("servicios")

        assert "NO VINCULANTE" in bloque["fuerza"]
        assert "NO es fuente de tarifas" in bloque["fuerza"]
        assert "siigo.com" in bloque["fuente"]["url"]
        assert "no rellenes el hueco" in bloque["advertencia"].lower()


class TestLasCifrasDelArticuloNoSonTarifas:
    def test_toda_cifra_viaja_separada_y_marcada_como_ejemplo(self):
        """Ninguna tarifa del artículo puede aparecer en el cuerpo conceptual.

        El modelo lee el dato y su etiqueta juntos: si el 0,772 % estuviera en la misma frase
        que la explicación del cálculo, sería indistinguible de una tarifa aplicable.
        """
        for pasaje in reteica_knowledge.recuperar("tarifa calculo base minima actividad", limite=9):
            cuerpo = pasaje["concepto"]
            # La regla es literal: en el cuerpo conceptual no entra ningún NÚMERO. Nombrar
            # la unidad («expresada en UVT», «se divide entre cien») es explicar el
            # mecanismo; escribir la cifra es entregar un dato que el modelo puede aplicar.
            assert not re.search(r"\d", cuerpo), f"el pasaje {pasaje['id']} lleva cifras"
            assert "%" not in cuerpo, f"el pasaje {pasaje['id']} lleva una tarifa en el cuerpo"

    def test_los_ejemplos_se_declaran_no_aplicables(self):
        ejemplos = [
            p["ejemplo_ilustrativo"]
            for p in reteica_knowledge.recuperar("tarifa calculo base minima actividad", limite=9)
            if p.get("ejemplo_ilustrativo")
        ]

        assert ejemplos, "los pasajes con cifras deben traer su ejemplo separado"
        for texto in ejemplos:
            assert "NO" in texto or "no es" in texto or "Ilustran" in texto or "Ilustra" in texto

    def test_el_ejemplo_del_articulo_conserva_su_aritmetica(self):
        """0,772 % = 0,00772 sobre 30.000.000 son 231.600. La conversión a decimal es un paso
        matemático, y el corpus debe enseñarla sin que se confunda con una tarifa."""
        calculo = next(
            p for p in reteica_knowledge.recuperar("calculo tarifa", limite=9) if p["id"] == "calculo"
        )

        assert "0,00772" in calculo["ejemplo_ilustrativo"]
        assert "231.600" in calculo["ejemplo_ilustrativo"]
        assert "no es una tarifa aplicable" in calculo["ejemplo_ilustrativo"]


class TestElBloqueVaPorDebajoDeTodoEnElPrompt:
    def test_se_numera_por_debajo_de_los_casos_contabilizados(self):
        secciones = EvidenceBundle(
            tarifas_reteica=[{"municipality_code": "11001", "percentage": 6.9}],
            casos_historicos=[{"documento_id": 1}],
            conocimiento_conceptual=reteica_knowledge.bloque_para_prompt("servicios"),
        ).as_prompt_sections()

        assert "5_conocimiento_conceptual_reteica" in secciones
        assert sorted(secciones) == [
            "1_tarifas_oficiales_reteica_por_municipio",
            "4_casos_contabilizados_similares",
            "5_conocimiento_conceptual_reteica",
        ]

    def test_sin_conocimiento_conceptual_el_prompt_no_trae_la_seccion(self):
        secciones = EvidenceBundle(tarifas_reteica=[{"percentage": 1}]).as_prompt_sections()

        assert "5_conocimiento_conceptual_reteica" not in secciones


class TestSoloEntraCuandoReteICAEstaEnEstudio:
    @pytest.mark.asyncio
    async def test_entra_si_reteica_es_candidata(self):
        bundle = await RetentionEvidenceRetriever(rag_client=None).build(
            document=_DOCUMENTO,
            tipos_candidatos={"reteica", "retefuente"},
            tarifas_retefuente=[],
            tarifas_reteica=[{"municipality_code": "11001", "percentage": 6.9}],
        )

        assert bundle.conocimiento_conceptual is not None

    @pytest.mark.asyncio
    async def test_no_entra_si_la_empresa_no_retiene_ica(self):
        """Doctrina de un tributo que no se puede practicar solo gasta contexto."""
        bundle = await RetentionEvidenceRetriever(rag_client=None).build(
            document=_DOCUMENTO,
            tipos_candidatos={"retefuente"},
            tarifas_retefuente=[{"concepto": "servicios", "tarifa": 4.0}],
            tarifas_reteica=[],
        )

        assert bundle.conocimiento_conceptual is None
