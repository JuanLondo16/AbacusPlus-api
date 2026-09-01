"""RF-08 · La capa determinística que comprueba lo que el modelo propuso.

Lo que se protege aquí es la diferencia entre pedir y garantizar. El prompt ya le dice al
modelo que tome la tarifa de la tabla, respete la base mínima y no le retenga a un
autorretenedor; estas pruebas comprueban que el sistema no depende de que obedezca.
"""

import pytest
from app.domain.services.retention_validation import RetentionValidator

_TARIFAS_FUENTE = [
    {"retention_concept": "servicios", "tarifa": 4.0, "base_minima_pesos": 209_496.0},
    {"retention_concept": "compras", "tarifa": 2.5, "base_minima_pesos": 1_413_998.0},
]

_TARIFAS_ICA = [
    {
        "id": 11,
        "municipality_code": "11001",
        "retention_concept": "servicios",
        "percentage": 9.66,
        "base_minima_pesos": 209_496.0,
    }
]


def _sugerencia(**kwargs) -> dict:
    base = {
        "tax_id": 10,
        "name": "Retefuente 4%",
        "type": "Retefuente",
        "percentage": 4.0,
        "taxable_base": 1_000_000.0,
    }
    base.update(kwargs)
    return base


class TestLaTarifaDebeExistirEnLaTablaOficial:
    """El catálogo trae once ReteFuente que solo se distinguen por el porcentaje del nombre.

    Que el modelo elija una del catálogo no prueba nada: prueba que existe como impuesto en
    SIIGO, no que sea la tarifa que corresponde a la operación. La tabla oficial es la única
    fuente que lo dice.
    """

    def test_acepta_la_que_coincide_con_una_fila(self):
        validator = RetentionValidator(tarifas_retefuente=_TARIFAS_FUENTE)

        assert validator.rechazo(_sugerencia()) is None

    def test_descarta_una_tarifa_que_no_esta_en_la_tabla(self):
        validator = RetentionValidator(tarifas_retefuente=_TARIFAS_FUENTE)

        motivo = validator.rechazo(_sugerencia(name="Retefuente 10%", percentage=10.0))

        assert motivo is not None
        assert "10%" in motivo and "tabla" in motivo

    def test_descarta_una_reteica_cuyo_id_no_esta_en_el_catalogo_cargado(self):
        """Desde la migración del 2026-08-31 se busca por `tax_id`, no por porcentaje: cada
        candidata de `integration_retentions` YA ES una fila completa (municipio + concepto +
        tarifa + base mínima), así que "está en la tabla" es "su id está en la tabla"."""
        validator = RetentionValidator(tarifas_reteica=_TARIFAS_ICA)

        motivo = validator.rechazo(
            _sugerencia(tax_id=999, name="ReteICA 4.14", type="ReteICA", percentage=4.14)
        )

        assert motivo is not None
        assert "ReteICA" in motivo

    def test_acepta_una_reteica_cuyo_id_esta_en_el_catalogo_cargado(self):
        validator = RetentionValidator(tarifas_reteica=_TARIFAS_ICA)

        motivo = validator.rechazo(
            _sugerencia(tax_id=11, name="ReteICA 9.66", type="ReteICA", percentage=9.66)
        )

        assert motivo is None


class TestBaseMinima:
    """Por debajo del tope de la tabla no se practica la retención."""

    def test_descarta_la_que_no_alcanza_ningun_tope_de_las_filas_compatibles(self):
        validator = RetentionValidator(tarifas_retefuente=_TARIFAS_FUENTE)

        motivo = validator.rechazo(_sugerencia(taxable_base=100_000.0))

        assert motivo is not None
        assert "base mínima" in motivo

    def test_acepta_la_que_supera_el_tope(self):
        validator = RetentionValidator(tarifas_retefuente=_TARIFAS_FUENTE)

        assert validator.rechazo(_sugerencia(taxable_base=250_000.0)) is None

    def test_convierte_el_tope_en_uvt_con_la_del_ano_del_documento(self):
        """El tope se guarda en UVT porque en pesos caduca cada enero."""
        validator = RetentionValidator(
            tarifas_retefuente=[{"tarifa": 4.0, "base_minima_uvt": 4}], uvt=52_374
        )

        # 4 UVT × 52.374 = 209.496 pesos.
        assert validator.rechazo(_sugerencia(taxable_base=209_496.0)) is None
        assert validator.rechazo(_sugerencia(taxable_base=209_000.0)) is not None

    def test_sin_uvt_conocida_no_compara_en_vez_de_usar_un_importe_caducado(self):
        validator = RetentionValidator(
            tarifas_retefuente=[{"tarifa": 4.0, "base_minima_uvt": 4}], uvt=None
        )

        assert validator.rechazo(_sugerencia(taxable_base=1.0)) is None

    def test_una_fila_sin_tope_no_bloquea_nada(self):
        validator = RetentionValidator(tarifas_retefuente=[{"tarifa": 4.0}])

        assert validator.rechazo(_sugerencia(taxable_base=1_000.0)) is None

    def test_tambien_aplica_a_reteica_encontrada_por_id(self):
        """La base mínima de ReteICA sale de la MISMA fila que resolvió el `tax_id`."""
        validator = RetentionValidator(tarifas_reteica=_TARIFAS_ICA)

        sugerencia = _sugerencia(
            tax_id=11, name="ReteICA 9.66", type="ReteICA", percentage=9.66, taxable_base=100_000.0
        )

        motivo = validator.rechazo(sugerencia)

        assert motivo is not None
        assert "base mínima" in motivo


class TestAlAutorretenedorNoSeLeRetieneEnLaFuente:
    """Respuesta literal del contador del cliente en el cuestionario de retenciones."""

    def test_descarta_la_retefuente_si_el_emisor_es_autorretenedor(self):
        validator = RetentionValidator(
            tarifas_retefuente=_TARIFAS_FUENTE,
            responsabilidades_emisor=[{"codigo": "O-15", "significado": "Autorretenedor"}],
        )

        motivo = validator.rechazo(_sugerencia())

        assert motivo is not None
        assert "autorretenedor" in motivo.lower()

    def test_no_afecta_a_la_reteica(self):
        """El contador lo dice explícitamente: la autorretención es de renta, no de ICA."""
        validator = RetentionValidator(
            tarifas_reteica=_TARIFAS_ICA,
            responsabilidades_emisor=[{"codigo": "O-15", "significado": "Autorretenedor"}],
        )

        sugerencia = _sugerencia(tax_id=11, name="ReteICA 9.66", type="ReteICA", percentage=9.66)

        assert validator.rechazo(sugerencia) is None


class TestReteIVA:
    def test_descarta_la_reteiva_si_la_factura_no_tiene_iva(self):
        validator = RetentionValidator(iva_documento=0)

        motivo = validator.rechazo(
            _sugerencia(name="ReteIVA 15%", type="ReteIVA", percentage=15.0, taxable_base=0)
        )

        assert motivo is not None

    def test_acepta_la_reteiva_cuando_hay_iva_facturado(self):
        validator = RetentionValidator(iva_documento=19_000)

        sugerencia = _sugerencia(
            name="ReteIVA 15%", type="ReteIVA", percentage=15.0, taxable_base=19_000
        )

        assert validator.rechazo(sugerencia) is None


class TestSoloLasTresRetencionesDeUnaCompra:
    """RF-08 nombra tres: ReteFuente, ReteICA y ReteIVA. El catálogo de Impuestos trae más.

    En el catálogo real del cliente conviven impoconsumo y autorretención. Ninguna de las dos
    es algo que el comprador le practique al proveedor, y proponerlas sería inventar una
    retención con un `tax_id` que existe —lo peor de los dos mundos, porque parece legítima.
    """

    def test_descarta_el_impoconsumo(self):
        validator = RetentionValidator()

        sugerencia = _sugerencia(name="Impoconsumo 8%", type="Impoconsumo", percentage=8.0)

        motivo = validator.rechazo(sugerencia)

        assert motivo is not None
        assert "impuesto del documento" in motivo

    def test_descarta_la_autorretencion(self):
        """«Es un cálculo que se hace sobre las ventas, mas no por las compras» (contador)."""
        validator = RetentionValidator()

        sugerencia = _sugerencia(name="autorretencion", type="Autorretencion", percentage=0.4)

        motivo = validator.rechazo(sugerencia)

        assert motivo is not None
        assert "ventas" in motivo

    def test_descarta_un_tributo_que_no_se_reconoce(self):
        """Ante lo desconocido, abstenerse: el contador puede registrarlo a mano."""
        validator = RetentionValidator()

        sugerencia = _sugerencia(name="Estampilla", type="Otra", percentage=1.0)

        assert validator.rechazo(sugerencia) is not None


class TestNoCorrigeNiInventa:
    @pytest.mark.parametrize("base", [0, -1])
    def test_una_base_no_positiva_no_produce_retencion(self, base):
        validator = RetentionValidator(tarifas_retefuente=_TARIFAS_FUENTE)

        assert validator.rechazo(_sugerencia(taxable_base=base)) is not None


class TestDeDondeSaleLaBaseMinima:
    """Manda la tabla importada; la UVT solo cubre lo que la tabla no trae.

    La tabla de tarifas se carga desde Excel justamente para poder actualizarla sin desplegar.
    Preferir una conversión calculada en el código sobre el importe que el contador escribió
    invertiría la jerarquía de fuentes de RF-08.
    """

    def test_usa_el_importe_en_pesos_que_trae_la_fila(self):
        fila = [{"tarifa": 4.0, "base_minima_uvt": 2, "base_minima_pesos": 104_748.0}]
        validator = RetentionValidator(tarifas_retefuente=fila, uvt=52_374)

        assert validator.rechazo(_sugerencia(taxable_base=104_748.0)) is None
        assert validator.rechazo(_sugerencia(taxable_base=100_000.0)) is not None

    def test_convierte_desde_uvt_cuando_la_fila_no_trae_pesos(self):
        """Es el caso de la tabla de ReteICA, que solo guarda el tope en UVT."""
        fila = [{"tarifa": 4.0, "base_minima_uvt": 2}]
        validator = RetentionValidator(tarifas_retefuente=fila, uvt=52_374)

        assert validator.rechazo(_sugerencia(taxable_base=104_748.0)) is None
        assert validator.rechazo(_sugerencia(taxable_base=100_000.0)) is not None
