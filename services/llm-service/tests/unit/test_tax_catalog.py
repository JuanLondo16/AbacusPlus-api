"""RF-08 · Lectura estructurada de la sección Impuestos.

Los datos de estas pruebas están calcados del catálogo real del tenant: los mismos tipos
(`Autorretencion`, `Impoconsumo`, `IVA`, `Retefuente`) y las mismas filas gemelas que dejó
combinar la sincronización con SIIGO y una importación de Excel («IVA 19%» / «IVA 19%.»).
"""

from app.domain.services.tax_catalog import (
    classify,
    document_tax_breakdown,
    retention_candidates,
)

_CATALOGO_REAL = [
    {
        "id": 23,
        "name": "autorretencion",
        "type": "Autorretencion",
        "percentage": 0.4,
        "active": True,
    },
    {
        "id": 29,
        "name": "autorretención.",
        "type": "Autorretencion",
        "percentage": 0.4,
        "active": True,
    },
    {"id": 16, "name": "Impoconsumo 8%", "type": "Impoconsumo", "percentage": 8.0, "active": True},
    {"id": 1, "name": "IVA 19%", "type": "IVA", "percentage": 19.0, "active": True},
    {"id": 28, "name": "IVA 19%.", "type": "IVA", "percentage": 19.0, "active": True},
    {"id": 21, "name": "Retefuente 1%", "type": "Retefuente", "percentage": 1.0, "active": True},
    {"id": 4, "name": "Retefuente 10%", "type": "Retefuente", "percentage": 10.0, "active": True},
]


class TestClasificacion:
    def test_reconoce_los_tipos_del_catalogo_real(self):
        assert classify({"type": "Retefuente"}) == "retefuente"
        assert classify({"type": "ReteICA"}) == "reteica"
        assert classify({"type": "ReteIVA"}) == "reteiva"
        assert classify({"type": "IVA"}) == "iva"
        assert classify({"type": "Impoconsumo"}) == "impoconsumo"
        assert classify({"type": "Autorretencion"}) == "autorretencion"

    def test_la_autorretencion_no_se_confunde_con_retefuente(self):
        """Su nombre contiene «retención»: clasificarla como ReteFuente sería el peor error."""
        assert classify({"type": "", "name": "autorretención."}) == "autorretencion"

    def test_ignora_tildes_espacios_y_puntuacion(self):
        assert classify({"type": "Rete ICA"}) == "reteica"
        assert classify({"type": "ReteICA."}) == "reteica"

    def test_cae_al_nombre_cuando_el_tipo_no_dice_nada(self):
        assert classify({"type": "", "name": "ReteIVA 15%"}) == "reteiva"

    def test_lo_que_no_reconoce_queda_sin_clase_en_vez_de_adivinarse(self):
        assert classify({"type": "Estampilla", "name": "Estampilla procultura"}) == ""


class TestCandidatasDelCatalogo:
    def test_solo_propone_las_tres_retenciones_de_una_compra(self):
        candidatas, _ = retention_candidates(_CATALOGO_REAL)

        assert {c["clase"] for c in candidatas} == {"retefuente"}
        assert sorted(c["id"] for c in candidatas) == [4, 21]

    def test_no_avisa_de_los_tributos_que_todo_catalogo_trae(self):
        """El IVA, el impoconsumo y la autorretención están siempre; avisar de ellos es ruido.

        Un aviso que aparece en cada sugerencia de cada documento no informa de nada: entrena
        al contador a ignorar todos los demás, incluido el que sí habla de su factura.
        """
        _, avisos = retention_candidates(_CATALOGO_REAL)

        assert avisos == []

    def test_colapsa_las_filas_gemelas_en_silencio(self):
        """Producen el mismo cálculo: cuál se use no es una decisión del contador.

        Lo único que debe garantizarse es elegir siempre la misma, para que la sugerencia no
        cambie entre ejecuciones. Avisarlo en cada documento era ruido sobre algo que no
        requiere acción.
        """
        catalogo = [
            {"id": 21, "name": "Retefuente 1%", "type": "Retefuente", "percentage": 1.0},
            {"id": 33, "name": "Retefuente 1%.", "type": "Retefuente", "percentage": 1.0},
        ]

        candidatas, avisos = retention_candidates(catalogo)

        assert [c["id"] for c in candidatas] == [21]
        assert avisos == []

    def test_dos_conceptos_con_la_misma_tarifa_NO_son_duplicados(self):
        """«Retefuente 4%» y «Retefuente Arriendo 4%» son retenciones distintas.

        Comparten tarifa, pero responden a conceptos tributarios distintos y en SIIGO cuelgan
        de cuentas distintas. Colapsarlas le quitaría al contador la opción correcta y
        contabilizaría contra la cuenta equivocada, sin que nada lo advirtiera.
        """
        catalogo = [
            {"id": 6, "name": "Retefuente 4%", "type": "Retefuente", "percentage": 4.0},
            {"id": 24, "name": "Retefuente Arriendo 4%", "type": "Retefuente", "percentage": 4.0},
        ]

        candidatas, avisos = retention_candidates(catalogo)

        assert sorted(c["id"] for c in candidatas) == [6, 24]
        assert avisos == []

    def test_descarta_una_fila_sin_porcentaje_y_lo_dice(self):
        catalogo = [
            {"id": 5, "name": "Retefuente sin tarifa", "type": "Retefuente", "percentage": 0}
        ]

        candidatas, avisos = retention_candidates(catalogo)

        assert candidatas == []
        assert any("sin porcentaje" in a for a in avisos)

    def test_excluye_las_filas_inactivas(self):
        catalogo = [
            {
                "id": 7,
                "name": "Retefuente 4%",
                "type": "Retefuente",
                "percentage": 4.0,
                "active": False,
            }
        ]

        assert retention_candidates(catalogo)[0] == []

    def test_un_catalogo_vacio_no_produce_candidatas_ni_falla(self):
        assert retention_candidates([]) == ([], [])


class TestImpuestosDelDocumento:
    """El IVA de la factura no es `total_taxes`: ese campo suma todos los impuestos."""

    def test_separa_el_iva_del_impoconsumo(self):
        documento = {
            "total_taxes": 27_000.0,
            "details": [
                {"id": 1, "subtotal": 100_000.0, "tax_id": 1, "tax_value": 19_000.0},
                {"id": 2, "subtotal": 100_000.0, "tax_id": 16, "tax_value": 8_000.0},
            ],
        }

        desglose = document_tax_breakdown(documento, _CATALOGO_REAL)

        assert desglose["iva"] == 19_000.0
        assert desglose["por_clase"]["impoconsumo"] == 8_000.0
        # La diferencia entre ambos queda visible en vez de desaparecer en un agregado.
        assert desglose["total_declarado"] == 27_000.0

    def test_sin_lineas_enlazadas_al_catalogo_declara_que_no_sabe(self):
        """Devolver `total_taxes` como si fuera IVA sería afirmar algo que no consta."""
        documento = {
            "total_taxes": 27_000.0,
            "details": [{"id": 1, "subtotal": 100_000.0, "tax_id": None, "tax_value": 27_000.0}],
        }

        desglose = document_tax_breakdown(documento, _CATALOGO_REAL)

        assert desglose["iva"] is None
        assert desglose["por_clase"]["sin_clasificar"] == 27_000.0

    def test_un_documento_sin_impuestos_no_inventa_ninguno(self):
        documento = {
            "total_taxes": 0,
            "details": [{"id": 1, "subtotal": 100_000.0, "tax_id": None, "tax_value": 0}],
        }

        desglose = document_tax_breakdown(documento, _CATALOGO_REAL)

        assert desglose["iva"] is None
        assert desglose["por_clase"] == {}

    def test_cada_renglon_conserva_su_impuesto_para_acotar_la_base(self):
        documento = {
            "total_taxes": 19_000.0,
            "details": [{"id": 58, "subtotal": 100_000.0, "tax_id": 1, "tax_value": 19_000.0}],
        }

        renglon = document_tax_breakdown(documento, _CATALOGO_REAL)["renglones"][0]

        assert renglon["detail_id"] == 58
        assert renglon["impuesto"] == "IVA 19%"
        assert renglon["clase"] == "iva"
        assert renglon["porcentaje"] == 19.0


class TestNadaSeDescartaEnSilencio:
    """El catálogo lo llena SIIGO, así que su vocabulario puede cambiar sin avisarnos.

    Si un rótulo nuevo dejara de reconocerse, la fila desaparecería de las candidatas y el
    contador solo vería «la IA no identificó retenciones aplicables» — indistinguible de que
    no procedieran. Ese es justo el fallo silencioso que RF-08 no puede permitirse.
    """

    def test_una_fila_con_tributo_no_reconocido_se_avisa(self):
        catalogo = [
            {
                "id": 50,
                "name": "Retencion municipal industria",
                "type": "Territorial",
                "percentage": 0.7,
                "active": True,
            }
        ]

        candidatas, avisos = retention_candidates(catalogo)

        assert candidatas == []
        assert any("no se reconoce el tributo" in a for a in avisos)
        assert any("Retencion municipal industria" in a for a in avisos)


class TestElDesgloseNoCreceSinLimite:
    """Una factura con cientos de líneas no puede inflar el prompt sin control.

    El coste y la latencia crecen con el prompt, y el detalle línea a línea aporta cada vez
    menos: sirve para acotar la base a unos renglones, no para leer la factura entera. Lo que
    NO se recorta son los agregados, porque de ellos sale la base de la ReteIVA.
    """

    def test_acota_el_detalle_pero_no_los_agregados(self):
        documento = {
            "total_taxes": 100 * 190.0,
            "details": [
                {"id": i, "subtotal": 1000.0, "tax_id": 1, "tax_value": 190.0} for i in range(100)
            ],
        }

        desglose = document_tax_breakdown(documento, _CATALOGO_REAL)

        assert len(desglose["renglones"]) == 20
        assert desglose["renglones_omitidos"] == 80
        # El IVA sale de las cien líneas, no de las veinte que viajan al prompt.
        assert desglose["iva"] == 19_000.0

    def test_sin_recorte_no_se_declara_nada(self):
        documento = {
            "total_taxes": 190.0,
            "details": [{"id": 1, "subtotal": 1000.0, "tax_id": 1, "tax_value": 190.0}],
        }

        assert "renglones_omitidos" not in document_tax_breakdown(documento, _CATALOGO_REAL)
