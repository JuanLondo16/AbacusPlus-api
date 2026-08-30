"""RF-08 · Un precedente contabilizado solo informa si las condiciones son comparables.

El sistema ya recuperaba causaciones CONTABILIZADAS y las rotulaba como precedente. Lo que no
hacía era decir **hasta qué punto se parecen**: el municipio del caso viajaba como un código
DANE suelto dentro de un JSON largo, junto al de la empresa, y comparar los dos quedaba a
cargo del modelo. Para ReteICA esa comparación no es un matiz —la tarifa de un municipio no
dice nada del de al lado—, así que se resuelve aquí, de forma determinística, y el modelo
recibe el juicio ya hecho.

Nada de esto cambia QUÉ se recupera: la búsqueda sigue siendo la misma, sobre las mismas
causaciones contabilizadas.
"""

import pytest
from app.application.services.retention_evidence import RetentionEvidenceRetriever

_DOCUMENTO = {
    "issuer_name": "ASEO INTEGRAL SAS",
    "issuer_nit": "900555111",
    "details": [{"id": 1, "description": "Servicios de aseo"}],
}


def _caso(municipio):
    return {
        "source_id": 7,
        "siigo_id": "abc-123",
        "similarity": 0.88,
        "content": "CAUSACIÓN CONTABILIZADA…",
        "metadata": {"issuer_nit": "900555111", "municipality_code": municipio},
    }


class _RagFalso:
    def __init__(self, resultados):
        self._resultados = resultados

    async def search(self, query, top_k=5, only_validated=False, filters=None):
        return self._resultados


async def _casos(municipio_del_caso, municipios_empresa):
    bundle = await RetentionEvidenceRetriever(
        rag_client=_RagFalso([_caso(municipio_del_caso)])
    ).build(
        document=_DOCUMENTO,
        tipos_candidatos={"reteica"},
        tarifas_retefuente=[],
        tarifas_reteica=[{"municipality_code": "11001", "percentage": 6.9}],
        municipios_reteica=municipios_empresa,
    )
    return bundle.casos_historicos


class TestLaComparabilidadSeCalcula:
    @pytest.mark.asyncio
    async def test_mismo_municipio_es_comparable(self):
        caso = (await _casos("11001", {"11001"}))[0]

        assert caso["comparabilidad"]["municipio_comparable"] is True
        assert caso["comparabilidad"]["municipio_del_caso"] == "11001"

    @pytest.mark.asyncio
    async def test_un_precedente_de_otra_jurisdiccion_se_marca_como_no_comparable(self):
        """El caso se causó donde esta empresa no retiene ICA: su ReteICA no sirve."""
        caso = (await _casos("05001", {"11001"}))[0]

        assert caso["comparabilidad"]["municipio_comparable"] is False

    @pytest.mark.asyncio
    async def test_sin_municipio_en_el_precedente_no_se_afirma_nada(self):
        """`null` es «no consta», no «coincide».

        El indexador deja el caso sin municipio cuando la empresa retiene en varios: prefiere
        no etiquetarlo antes que atribuirle el equivocado. Convertir aquí esa abstención en
        `false` descartaría precedentes válidos; en `true`, propagaría la tarifa de otra
        ciudad.
        """
        caso = (await _casos("", {"11001"}))[0]

        assert caso["comparabilidad"]["municipio_comparable"] is None

    @pytest.mark.asyncio
    async def test_sin_municipios_configurados_tampoco_se_afirma_nada(self):
        caso = (await _casos("11001", set()))[0]

        assert caso["comparabilidad"]["municipio_comparable"] is None

    @pytest.mark.asyncio
    async def test_el_precedente_enumera_lo_que_hay_que_verificar(self):
        """La lista es la del contador: municipio, actividad, tercero, operación, tarifa."""
        comparabilidad = (await _casos("11001", {"11001"}))[0]["comparabilidad"]

        verificar = " ".join(comparabilidad["verificar_antes_de_reutilizar"]).lower()
        for condicion in ("municipio", "actividad", "tercero", "operación", "tarifa"):
            assert condicion in verificar

    @pytest.mark.asyncio
    async def test_el_precedente_conserva_su_comprobante_y_su_procedencia(self):
        """La comparabilidad se añade; no desplaza nada de lo que ya viajaba."""
        caso = (await _casos("11001", {"11001"}))[0]

        assert caso["comprobante_siigo"] == "abc-123"
        assert caso["mismo_proveedor"] is True
        assert caso["comparabilidad"]["mismo_proveedor"] is True
