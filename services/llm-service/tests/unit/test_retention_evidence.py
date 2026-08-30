"""RF-08 · Recuperación de casos contabilizados y separación de fuentes.

Lo que se demuestra aquí no es que la recuperación funcione, sino que **no contamina**: que
un precedente llega marcado como precedente, que una tarifa llega marcada como vinculante, y
que el historial se busca por lo que hace comparables dos facturas —el tercero, el
concepto— y no por un parecido textual cualquiera.
"""


from app.application.services.retention_evidence import (
    EvidenceBundle,
    RetentionEvidenceRetriever,
)

_DOCUMENT = {
    "issuer_name": "FERRETERIA EL TORNILLO SAS",
    "issuer_nit": "900123456-7",
    "details": [
        {"id": 11, "description": "Mantenimiento locativo de oficinas", "subtotal": 150000.0},
    ],
}

_CASO = {
    "source_id": 42,
    "siigo_id": "a1b2c3",
    "similarity": 0.91,
    "content": "CAUSACIÓN CONTABILIZADA…\nRetenciones practicadas:\n  - ReteFuente servicios",
    "metadata": {
        "issuer_nit": "900123456",
        "retention_types": ["retefuente"],
        "municipality_code": "11001",
    },
}


class RagFalso:
    """Registra cada búsqueda para poder afirmar CÓMO se buscó, no solo qué se obtuvo."""

    def __init__(self, resultados=None, por_filtro=None):
        self.llamadas = []
        self._resultados = resultados if resultados is not None else []
        self._por_filtro = por_filtro or {}

    async def search(self, query, top_k=5, only_validated=False, filters=None):
        self.llamadas.append(
            {
                "query": query,
                "top_k": top_k,
                "only_validated": only_validated,
                "filters": filters or {},
            }
        )
        clave = tuple(sorted((filters or {}).items(), key=lambda kv: kv[0]))
        if clave in self._por_filtro:
            return self._por_filtro[clave]
        return self._resultados


# Criterios tal como llegan del integration-config-service: datos del tenant, no una
# constante de este servicio.
_CRITERIOS = [
    {
        "tema": "retefuente",
        "pregunta": "¿Cómo se determina el concepto?",
        "criterio": "Por la descripción de la línea.",
    },
    {
        "tema": "reteiva",
        "pregunta": "¿Sobre qué base se calcula?",
        "criterio": "Sobre el IVA, al 15%.",
    },
    {
        "tema": "proceso",
        "pregunta": "¿Qué información se necesita?",
        "criterio": "Régimen, responsabilidad fiscal y ubicación.",
    },
]


async def _build(rag, tipos=None, criterios=None):
    return await RetentionEvidenceRetriever(rag_client=rag).build(
        document=_DOCUMENT,
        tipos_candidatos=tipos if tipos is not None else {"retefuente"},
        tarifas_retefuente=[{"retention_concept": "Servicios generales", "rate_percentage": 4}],
        tarifas_reteica=[{"municipality_code": "11001", "percentage": 0.966}],
        criterios_contador=_CRITERIOS if criterios is None else criterios,
    )


class TestBusquedaDeCasos:
    async def test_solo_se_buscan_causaciones_contabilizadas(self):
        """RF-08: un documento aprobado pero no contabilizado no es precedente."""
        rag = RagFalso(resultados=[_CASO])

        await _build(rag)

        assert all(ll["only_validated"] is True for ll in rag.llamadas)

    async def test_primero_se_busca_por_el_mismo_proveedor(self):
        """El filtro por NIT es lo que convierte «vecino textual» en «precedente».

        La retención depende del régimen y las responsabilidades del tercero, que son suyos.
        Un caso de otro proveedor con una descripción parecida no dice nada sobre este.
        """
        rag = RagFalso(resultados=[_CASO])

        bundle = await _build(rag)

        assert rag.llamadas[0]["filters"] == {"issuer_nit": "900123456"}
        assert bundle.traza_recuperacion["estrategia"] == "mismo_proveedor"
        assert bundle.casos_historicos[0]["mismo_proveedor"] is True

    async def test_el_nit_se_normaliza_igual_que_al_indexar(self):
        """'900123456-7' debe buscar '900123456'.

        Si una parte guarda el NIT con dígito de verificación y la otra busca sin él, el
        historial del proveedor no se encuentra nunca y el sistema aparenta no haber
        aprendido nada pese a tener los casos indexados.
        """
        rag = RagFalso(resultados=[_CASO])

        await _build(rag)

        assert rag.llamadas[0]["filters"]["issuer_nit"] == "900123456"

    async def test_sin_historial_del_proveedor_se_amplia_al_concepto(self):
        """Un proveedor nuevo no tiene precedentes propios, pero el concepto sí."""
        rag = RagFalso(
            por_filtro={(("issuer_nit", "900123456"),): []},
            resultados=[dict(_CASO, metadata={"issuer_nit": "800999888"})],
        )

        bundle = await _build(rag)

        assert len(rag.llamadas) == 2
        assert rag.llamadas[1]["filters"] == {}
        assert bundle.traza_recuperacion["estrategia"] == "concepto_similar_otros_proveedores"
        # Marcado explícitamente: su régimen puede ser otro, así que vale menos.
        assert bundle.casos_historicos[0]["mismo_proveedor"] is False

    async def test_la_consulta_describe_la_operacion_no_solo_al_emisor(self):
        """El texto busca lo que el filtro no puede: de qué trata la factura.

        Según el contador, el concepto sale de «el nombre del producto o la descripción», y
        es donde más errores se cometen. Buscar solo por el nombre del proveedor
        desaprovecha justo la señal que discrimina el concepto.
        """
        rag = RagFalso(resultados=[_CASO])

        await _build(rag)

        assert "Mantenimiento locativo de oficinas" in rag.llamadas[0]["query"]

    async def test_sin_rag_la_sugerencia_sigue_adelante(self):
        """Un sistema recién estrenado no tiene historial y debe funcionar igual."""
        bundle = await RetentionEvidenceRetriever(rag_client=None).build(
            document=_DOCUMENT,
            tipos_candidatos={"retefuente"},
            tarifas_retefuente=[],
            tarifas_reteica=[],
        )

        assert bundle.casos_historicos == []
        assert bundle.traza_recuperacion["estrategia"] == "ninguna"

    async def test_un_fallo_del_rag_no_rompe_la_sugerencia(self):
        class RagRoto:
            async def search(self, *a, **kw):
                raise RuntimeError("rag caído")

        bundle = await _build(RagRoto())

        assert bundle.casos_historicos == []
        assert bundle.tarifas_retefuente  # las reglas siguen intactas


class TestSeparacionDeFuentes:
    async def test_cada_bloque_declara_su_fuerza(self):
        """Sin la etiqueta, veinte precedentes pesan más que la tabla vigente."""
        bundle = await _build(RagFalso(resultados=[_CASO]))
        secciones = bundle.as_prompt_sections()

        assert "VINCULANTE" in secciones["1_tarifas_oficiales_retefuente_por_concepto"]["fuerza"]
        assert "VINCULANTE" in secciones["1_tarifas_oficiales_reteica_por_municipio"]["fuerza"]
        assert "ORIENTATIVO" in secciones["3_criterios_del_contador"]["fuerza"]
        assert "PRECEDENTE" in secciones["4_casos_contabilizados_similares"]["fuerza"]

    async def test_los_casos_advierten_que_no_son_norma(self):
        bundle = await _build(RagFalso(resultados=[_CASO]))
        uso = bundle.as_prompt_sections()["4_casos_contabilizados_similares"]["uso"]

        assert "NO determinan la decisión actual" in uso
        assert "frecuencia" in uso

    async def test_los_criterios_del_contador_entran_como_fuente_propia(self):
        bundle = await _build(RagFalso(), tipos={"reteiva"})
        seccion = bundle.as_prompt_sections()["3_criterios_del_contador"]

        temas = {c["tema"] for c in seccion["criterios"]}
        assert "reteiva" in temas
        assert "proceso" in temas  # el proceso general gobierna siempre
        assert "retefuente" not in temas  # no era candidata: no gasta contexto
        assert "contador" in seccion["fuente"].lower()

    async def test_sin_criterios_configurados_la_sugerencia_sigue(self):
        """Un tenant que aún no registró criterios se apoya en las fuentes vinculantes."""
        bundle = await _build(RagFalso(), criterios=[])

        assert bundle.criterios_contador == []
        assert "3_criterios_del_contador" not in bundle.as_prompt_sections()
        assert bundle.tarifas_retefuente  # las tablas siguen mandando

    async def test_cada_caso_conserva_su_comprobante_de_siigo(self):
        """La trazabilidad exige poder señalar un asiento concreto, no «el histórico»."""
        bundle = await _build(RagFalso(resultados=[_CASO]))

        assert bundle.casos_historicos[0]["comprobante_siigo"] == "a1b2c3"
        assert bundle.casos_historicos[0]["documento_id"] == 42

    async def test_el_caso_no_se_recorta_hasta_perder_las_retenciones(self):
        """El límite anterior (200 caracteres para los tres casos) los hacía inútiles.

        Las retenciones van al final del texto de una causación, así que recortar en bloque
        eliminaba justo lo que se quería aprender.
        """
        bundle = await _build(RagFalso(resultados=[_CASO]))

        assert "Retenciones practicadas" in bundle.casos_historicos[0]["causacion"]


class TestBundleVacio:
    def test_un_paquete_sin_evidencia_no_aporta_secciones(self):
        """Sin fuentes no se inventan bloques vacíos que el modelo pueda malinterpretar."""
        assert EvidenceBundle().as_prompt_sections() == {}
