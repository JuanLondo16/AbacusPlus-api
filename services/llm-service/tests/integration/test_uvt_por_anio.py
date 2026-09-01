"""RF-08: las bases mínimas de ReteICA se expresan con la UVT del año del documento.

La UVT cambia cada año. Un importe en pesos incrustado en el prompt caduca en enero sin que
nada lo señale, y el modelo pasaría a evaluar bases mínimas con una cifra obsoleta: una
retención que no se practica cuando debía, o al revés. Estas pruebas fijan el comportamiento
que evita ese error silencioso.
"""

from datetime import date

from app.application.use_cases.suggest_retentions import (
    _UVT_POR_ANIO,
    _anio_documento,
    _formatear_base_uvt,
    _system_prompt,
)

# ── Año aplicable ──────────────────────────────────────────────────────────────


def test_se_usa_el_ano_del_documento_y_no_el_de_hoy():
    """Una factura de diciembre contabilizada en enero se evalúa con la UVT de diciembre."""
    assert _anio_documento({"date": "2026-12-28"}) == 2026


def test_admite_una_fecha_con_hora():
    assert _anio_documento({"date": "2026-08-11T10:30:00"}) == 2026


def test_sin_fecha_se_recurre_al_ano_en_curso():
    assert _anio_documento({}) == date.today().year


def test_una_fecha_ilegible_no_rompe_la_sugerencia():
    """Preferible una aproximación a que falle la sugerencia entera por un dato mal formado."""
    assert _anio_documento({"date": "no-es-una-fecha"}) == date.today().year


# ── Expresión de la base ───────────────────────────────────────────────────────


def test_con_uvt_conocida_la_base_se_expresa_tambien_en_pesos():
    texto = _formatear_base_uvt(4, 2026)
    assert texto.startswith("4 UVT")
    assert str(4 * _UVT_POR_ANIO[2026])[:3] in texto.replace(".", "")


def test_sin_uvt_del_ano_la_base_queda_solo_en_uvt():
    """Nunca se inventa un importe: es preferible una unidad correcta a una cifra caducada."""
    anio_sin_tabla = max(_UVT_POR_ANIO) + 5
    assert _formatear_base_uvt(4, anio_sin_tabla) == "4 UVT"


# ── Prompt resultante ──────────────────────────────────────────────────────────


def test_el_prompt_no_conserva_marcadores_sin_sustituir():
    prompt = _system_prompt(2026)
    assert "__BASE_ICA_SERVICIOS__" not in prompt
    assert "__BASE_ICA_COMPRAS__" not in prompt


def test_el_prompt_ya_no_fija_los_topes_de_bogota():
    """Las bases de ReteICA salen de la tabla, no del prompt.

    El ICA es territorial: cada municipio fija su tope y no hay uniformidad nacional. Con los
    valores de Bogotá escritos aquí (4 y 27 UVT), contabilizar en Bucaramanga —que pide 25 y
    50— proponía ReteICA sobre facturas que no la causan. Ahora cada fila de la tabla trae su
    `minimum_base_uvt` y el prompt manda leerla de ahí.
    """
    prompt = _system_prompt(2026)

    assert "Base mínima en Bogotá" not in prompt
    assert "base_minima_uvt" in prompt
    assert "lo fija cada municipio" in prompt.lower()
