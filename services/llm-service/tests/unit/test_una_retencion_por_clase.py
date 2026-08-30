"""RF-08 · una sola retención por clase en la propuesta del modelo.

El prompt ya lo pide —«UNA SOLA retención por tipo. No propongas dos ReteFuente para el mismo
documento»— y `_excluding_registered_types` lo hace cumplir frente a lo que el documento ya
tiene registrado. Faltaba comprobarlo sobre la propia salida del modelo: la deduplicación de
`_parse_response` es por `tax_id`, y el catálogo trae once ReteFuente que solo se distinguen
por el porcentaje del nombre, así que dos ids distintos de la misma clase pasaban los dos.

El caso que lo destapó: una factura de prestación de servicios sobre la que se propusieron
Retefuente 11% y Retefuente 3,5%, ambas sobre la misma base de $1.750.905. Sumadas retienen
$253.881 donde corresponde una sola de las dos.

Se descartan LAS DOS, no se elige una. Cuál de las dos tarifas corresponde depende del
concepto tributario de la operación, que es justo lo que no se puede deducir sin criterio;
elegir la primera, o la de mayor confianza, sería acertar por aproximación. Es la misma
doctrina que sigue `retention_validation.py`: ante la duda, abstenerse y decirlo.
"""

from app.application.use_cases.suggest_retentions import SuggestRetentionsUseCase


def _sugerencia(tax_id: int, clase: str, nombre: str, pct: float) -> dict:
    return {
        "tax_id": tax_id,
        "name": nombre,
        "type": nombre.split()[0],
        "clase": clase,
        "percentage": pct,
        "taxable_base": 1_750_905.0,
        "value": round(1_750_905.0 * pct / 100, 2),
    }


_RETEFUENTE_11 = _sugerencia(101, "retefuente", "Retefuente 11%", 11.0)
_RETEFUENTE_35 = _sugerencia(102, "retefuente", "Retefuente 3.5%", 3.5)
_RETEICA = _sugerencia(201, "reteica", "ReteICA 9.66", 9.66)


def _clases(items):
    return [i["clase"] for i in items]


def test_dos_retefuente_se_descartan_las_dos():
    warnings: list[str] = []
    result = SuggestRetentionsUseCase._single_per_class(
        [_RETEFUENTE_11, _RETEFUENTE_35], warnings
    )
    assert result == []
    assert len(warnings) == 1
    # El aviso nombra las dos tarifas en conflicto: el contador tiene que poder registrar a
    # mano la que corresponda, y para eso necesita saber entre cuáles se dudaba.
    assert "11%" in warnings[0] and "3.5%" in warnings[0]


def test_el_conflicto_no_arrastra_a_otras_clases():
    """Una ReteICA válida sobrevive al descarte de las dos ReteFuente."""
    warnings: list[str] = []
    result = SuggestRetentionsUseCase._single_per_class(
        [_RETEFUENTE_11, _RETEICA, _RETEFUENTE_35], warnings
    )
    assert _clases(result) == ["reteica"]
    assert len(warnings) == 1


def test_una_por_clase_pasa_intacta():
    warnings: list[str] = []
    result = SuggestRetentionsUseCase._single_per_class([_RETEFUENTE_11, _RETEICA], warnings)
    assert result == [_RETEFUENTE_11, _RETEICA]
    assert warnings == []


def test_sin_sugerencias_no_avisa():
    warnings: list[str] = []
    assert SuggestRetentionsUseCase._single_per_class([], warnings) == []
    assert warnings == []


def test_tres_de_la_misma_clase_tambien_se_descartan():
    """El conflicto no es «dos»: es «más de una». Tres tarifas no son más decidibles."""
    warnings: list[str] = []
    tercera = _sugerencia(103, "retefuente", "Retefuente 4%", 4.0)
    result = SuggestRetentionsUseCase._single_per_class(
        [_RETEFUENTE_11, _RETEFUENTE_35, tercera], warnings
    )
    assert result == []
    assert len(warnings) == 1
