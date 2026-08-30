"""Los municipios de ReteICA salen de las tarifas cargadas, no del perfil fiscal.

Antes vivían en dos sitios: la lista `municipios` del perfil fiscal y la tabla de tarifas de
ReteICA. Solo la segunda lleva la tarifa, y sin tarifa no se propone ReteICA, así que la
primera únicamente podía repetir a la segunda o contradecirla. Estas pruebas fijan que ahora
hay una sola fuente y que lo que ve el modelo sale de ella.
"""

from app.application.services.retention_evidence import EvidenceBundle
from app.application.use_cases.suggest_retentions import SuggestRetentionsUseCase

_ICA_RATES = [
    {"municipality_code": "11001", "municipality_name": "Bogotá D.C.", "percentage": 0.966},
    {"municipality_code": "05001", "municipality_name": "Medellín", "percentage": 0.7},
]

_PROFILE = {
    "agente_retencion_renta": True,
    "agente_retencion_ica": True,
    "agente_retencion_iva": False,
    "autorretenedor_renta": False,
    "gran_contribuyente": False,
    "responsable_iva": True,
    "regimen": "ordinario",
    "notas": None,
}

_DOCUMENT = {"receiver_name": "IKBO SAS", "receiver_nit": "901000001"}


# El caso de uso se construye sin dependencias: estas pruebas solo ejercitan el armado del
# prompt, que no toca el modelo ni ningún cliente HTTP.
def _use_case() -> SuggestRetentionsUseCase:
    return object.__new__(SuggestRetentionsUseCase)


def _buyer_block(ica_rates):
    return _use_case()._buyer_block(_DOCUMENT, _PROFILE, ica_rates)


class TestMunicipiosDerivados:
    def test_los_municipios_salen_de_las_tarifas(self):
        block = _buyer_block(_ICA_RATES)

        assert block["municipios_donde_retiene_ica"] == [
            {"codigo": "11001", "nombre": "Bogotá D.C."},
            {"codigo": "05001", "nombre": "Medellín"},
        ]

    def test_sin_tarifas_no_hay_municipios(self):
        """Sin tarifa no se retiene en ninguna parte: la lista vacía es la respuesta correcta.

        Es el caso que antes quedaba incoherente: el perfil declaraba Bogotá, la tabla de
        tarifas estaba vacía, y el modelo recibía un municipio en el que no podía calcular nada.
        """
        assert _buyer_block([])["municipios_donde_retiene_ica"] == []
        assert _buyer_block(None)["municipios_donde_retiene_ica"] == []

    def test_no_se_repiten_municipios_con_varias_tarifas(self):
        """Un municipio con varias bandas de actividad es un solo municipio."""
        rates = [
            {"municipality_code": "11001", "municipality_name": "Bogotá D.C.", "percentage": 0.966},
            {"municipality_code": "11001", "municipality_name": "Bogotá D.C.", "percentage": 1.104},
        ]

        assert _buyer_block(rates)["municipios_donde_retiene_ica"] == [
            {"codigo": "11001", "nombre": "Bogotá D.C."}
        ]

    def test_se_ignoran_las_filas_sin_codigo(self):
        rates = [{"municipality_code": "", "municipality_name": "Sin código", "percentage": 1.0}]

        assert _buyer_block(rates)["municipios_donde_retiene_ica"] == []

    def test_el_perfil_sigue_mandando_sobre_si_la_empresa_retiene(self):
        """La tabla dice dónde y cuánto; el perfil sigue diciendo si la empresa es agente."""
        block = _buyer_block(_ICA_RATES)

        assert block["es_agente_retencion"]["ica"] is True
        assert "municipios" not in block


class TestTarifasEnElPrompt:
    def test_las_tarifas_de_reteica_llegan_al_modelo(self):
        """Se cargaban para decidir si ReteICA podía proponerse, pero no se enviaban.

        El sistema le ordenaba al modelo usar «únicamente la tarifa de la tabla oficial» sin
        pasarle esa tabla, así que la única salida que le quedaba era estimarla. Ahora viajan
        dentro del paquete de evidencia, rotuladas como fuente vinculante.
        """
        prompt = _use_case()._build_prompt(
            document=_DOCUMENT,
            candidates=[{"id": 2, "type": "reteica", "name": "ReteICA 9.66"}],
            issuer=None,
            evidence=EvidenceBundle(tarifas_reteica=_ICA_RATES),
            profile=_PROFILE,
            ica_rates=_ICA_RATES,
        )

        assert "tarifas_oficiales_reteica_por_municipio" in prompt
        assert "0.966" in prompt
        assert "Medellín" in prompt
        # La tabla debe llegar rotulada: sin la etiqueta, un precedente histórico compite
        # de tú a tú con la tarifa vigente.
        assert "VINCULANTE" in prompt

    def test_sin_tarifas_no_se_incluye_la_seccion(self):
        prompt = _use_case()._build_prompt(
            document=_DOCUMENT,
            candidates=[],
            issuer=None,
            evidence=EvidenceBundle(),
            profile=_PROFILE,
            ica_rates=[],
        )

        assert "tarifas_oficiales_reteica_por_municipio" not in prompt


class TestBaseMinimaPorMunicipio:
    """El ICA es territorial: cada municipio fija su tope y no hay uniformidad nacional.

    Bogotá pide 4 UVT en servicios y 27 en compras; Cali 3 y 15; Bucaramanga 25 y 50. Estaban
    fijos en el prompt con los valores de Bogotá, así que en Bucaramanga el sistema proponía
    ReteICA sobre facturas que no la causan: todo el rango entre 4 y 25 UVT.
    """

    _RATES = [
        {"municipality_code": "11001", "retention_concept": "servicios",
         "percentage": 0.966, "minimum_base_uvt": 4},
        {"municipality_code": "68001", "retention_concept": "servicios",
         "percentage": 0.7, "minimum_base_uvt": 25},
    ]

    def test_la_base_se_convierte_a_pesos_con_la_uvt_del_anio(self):
        salida = _use_case()._con_base_en_pesos(self._RATES, 52_374)

        # UVT 2026 = 52.374
        assert salida[0]["base_minima_uvt"] == 4
        assert salida[0]["base_minima_pesos"] == 209496.0
        assert salida[1]["base_minima_pesos"] == 1309350.0

    def test_cada_municipio_conserva_su_propio_tope(self):
        """Lo que fallaba antes: un único tope aplicado a todos los municipios."""
        salida = _use_case()._con_base_en_pesos(self._RATES, 52_374)

        assert salida[0]["base_minima_uvt"] != salida[1]["base_minima_uvt"]

    def test_sin_uvt_conocida_se_deja_solo_la_unidad(self):
        """Preferible una unidad correcta a un importe caducado."""
        salida = _use_case()._con_base_en_pesos(self._RATES, None)

        assert salida[0]["base_minima_uvt"] == 4
        assert "base_minima_pesos" not in salida[0]

    def test_una_fila_sin_tope_no_inventa_ninguno(self):
        salida = _use_case()._con_base_en_pesos(
            [{"municipality_code": "05001", "percentage": 0.7, "minimum_base_uvt": None}], 52_374
        )

        assert "base_minima_uvt" not in salida[0]
        assert "base_minima_pesos" not in salida[0]

    def test_la_base_llega_al_prompt(self):
        prompt = _use_case()._build_prompt(
            document=_DOCUMENT,
            candidates=[{"id": 2, "type": "reteica", "name": "ReteICA 9.66"}],
            issuer=None,
            evidence=EvidenceBundle(
                tarifas_reteica=_use_case()._con_base_en_pesos(self._RATES, 52_374)
            ),
            profile=_PROFILE,
        )

        assert "base_minima_uvt" in prompt
        assert "1309350" in prompt.replace(".0", "")


class TestLaUVTSeDeduceDeLaTablaImportada:
    """Un año nuevo o un decreto se resuelven cargando el Excel, no desplegando código.

    La tabla de ReteFuente trae cada tope en UVT y en pesos. Esas dos columnas, divididas, dan
    la UVT con la que el contador construyó el archivo — la que él considera vigente. Es el
    mismo principio por el que las tarifas viven en una tabla y no en el repositorio.
    """

    def test_la_deduce_de_las_dos_columnas_de_la_tabla(self):
        from app.application.use_cases.suggest_retentions import _uvt_efectiva

        rates = [
            {"base_minima_uvt": 10, "base_minima_pesos": 523_740.0},
            {"base_minima_uvt": 2, "base_minima_pesos": 104_748.0},
        ]

        assert _uvt_efectiva(rates, 2026) == 52_374

    def test_una_fila_mal_escrita_no_desplaza_el_calculo(self):
        """Se toma la mediana: una conversión errónea se ignora sin tener que detectarla."""
        from app.application.use_cases.suggest_retentions import _uvt_efectiva

        rates = [
            {"base_minima_uvt": 10, "base_minima_pesos": 523_740.0},
            {"base_minima_uvt": 2, "base_minima_pesos": 104_748.0},
            {"base_minima_uvt": 27, "base_minima_pesos": 1.0},  # dedo suelto
        ]

        assert _uvt_efectiva(rates, 2026) == 52_374

    def test_una_uvt_de_otro_ano_se_deduce_igual(self):
        """Es el caso que importa: en 2027 nadie tiene que tocar el código."""
        from app.application.use_cases.suggest_retentions import _uvt_efectiva

        rates = [{"base_minima_uvt": 10, "base_minima_pesos": 550_000.0}]

        assert _uvt_efectiva(rates, 2027) == 55_000

    def test_sin_tabla_utilizable_cae_al_calendario(self):
        from app.application.use_cases.suggest_retentions import _uvt_efectiva

        assert _uvt_efectiva([], 2026) == 52_374
        assert _uvt_efectiva([{"base_minima_uvt": 0, "base_minima_pesos": 0}], 2026) == 52_374

    def test_sin_tabla_y_sin_calendario_no_se_inventa_nada(self):
        from app.application.use_cases.suggest_retentions import _uvt_efectiva

        assert _uvt_efectiva([], 2031) is None
