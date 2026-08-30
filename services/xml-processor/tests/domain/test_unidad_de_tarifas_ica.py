"""Una tabla de ReteICA no puede mezclar unidades.

Lo que ocurrió de verdad
------------------------
El Excel importado dejó la tabla así:

    Bogotá · servicios  → 9.660000   (por mil, = 0,966 %)
    Bogotá · compras    → 1.104000   (porcentaje, = 11,04 por mil)

Las dos cifras son correctas por separado y describen tarifas reales. Mezcladas en la misma
tabla son una bomba: quien las lea aplicará una convención a las dos, y sobre la que esté en
la otra unidad retendrá **diez veces de más o de menos** sobre dinero de un tercero.

El sistema lo detectó al sugerir —RF-08 se negó a proponer la ReteICA y explicó por qué— pero
eso es tarde y depende de que alguien pida una sugerencia. El sitio donde hay que detectarlo
es la **importación**, que es cuando el dato entra.

Por qué se rechaza en vez de convertir
---------------------------------------
Convertir exige saber cuál de las dos filas está bien, y eso no se puede deducir del número:
1,104 es una tarifa plausible en por mil (municipios pequeños las tienen) y 11,04 lo es en
porcentaje (ninguno, pero el sistema no conoce el catastro tributario colombiano). Elegir por
nuestra cuenta sería exactamente la clase de suposición que no se puede permitir cuando el
resultado se descuenta del pago a un proveedor.

Se rechaza el archivo **entero**, nombrando las filas, para que el contador unifique el origen.
Importar la mitad buena dejaría la tabla incoherente igual, y con menos rastro.
"""

import pytest
from app.domain.services.ica_rate_units import (
    UMBRAL_POR_MIL,
    UnidadesMezcladasError,
    verificar_unidad_coherente,
)


def _fila(municipio, concepto, tarifa):
    return {
        "municipality_code": municipio,
        "municipality_name": municipio,
        "retention_concept": concepto,
        "percentage": tarifa,
    }


class TestTablaCoherente:
    def test_todas_por_mil_se_acepta(self):
        """Es la convención del catálogo de SIIGO, verificada contra el ambiente real."""
        filas = [
            _fila("11001", "servicios", 9.66),
            _fila("11001", "compras", 11.04),
            _fila("68001", "servicios", 7.0),
        ]
        verificar_unidad_coherente(filas)  # no lanza

    def test_todas_en_porcentaje_se_acepta(self):
        """Si el contador decide usar porcentaje, coherente también es válido."""
        filas = [
            _fila("11001", "servicios", 0.966),
            _fila("11001", "compras", 1.104),
        ]
        verificar_unidad_coherente(filas)

    def test_una_tabla_vacia_no_estalla(self):
        verificar_unidad_coherente([])
        verificar_unidad_coherente(None)

    def test_una_sola_fila_siempre_es_coherente(self):
        verificar_unidad_coherente([_fila("11001", "servicios", 9.66)])


class TestTablaConUnidadesMezcladas:
    def test_rechaza_el_archivo_entero(self):
        """El caso real del cliente: 9.66 y 1.104 en la misma tabla."""
        filas = [
            _fila("11001", "servicios", 9.66),
            _fila("11001", "compras", 1.104),
        ]
        with pytest.raises(UnidadesMezcladasError):
            verificar_unidad_coherente(filas)

    def test_el_mensaje_nombra_las_filas_de_cada_unidad(self):
        """El contador tiene que poder ir al Excel y arreglarlo sin adivinar cuál falla."""
        filas = [
            _fila("11001", "servicios", 9.66),
            _fila("11001", "compras", 1.104),
        ]
        with pytest.raises(UnidadesMezcladasError) as exc:
            verificar_unidad_coherente(filas)
        mensaje = str(exc.value)
        assert "servicios" in mensaje
        assert "compras" in mensaje
        assert "9.66" in mensaje
        assert "1.104" in mensaje

    def test_el_mensaje_explica_la_consecuencia(self):
        """No basta con «datos inválidos»: hay que decir por qué importa."""
        filas = [_fila("11001", "servicios", 9.66), _fila("11001", "compras", 1.104)]
        with pytest.raises(UnidadesMezcladasError) as exc:
            verificar_unidad_coherente(filas)
        assert "diez veces" in str(exc.value).lower()

    def test_el_mensaje_no_elige_por_el_contador(self):
        """Se le pide que unifique, no se le dice cuál es la buena: no lo sabemos."""
        filas = [_fila("11001", "servicios", 9.66), _fila("11001", "compras", 1.104)]
        with pytest.raises(UnidadesMezcladasError) as exc:
            verificar_unidad_coherente(filas)
        assert "unifique" in str(exc.value).lower()


class TestElUmbralQueSepara:
    def test_el_umbral_esta_declarado(self):
        """Separa las dos convenciones. Las tarifas de ICA en Colombia van de 2 a 14 por
        mil, es decir de 0,2 % a 1,4 %: no hay solapamiento entre las dos escalas."""
        assert 1.4 < UMBRAL_POR_MIL < 2.0

    def test_una_tarifa_justo_bajo_el_umbral_es_porcentaje(self):
        filas = [_fila("11001", "a", 1.4), _fila("11001", "b", 1.104)]
        verificar_unidad_coherente(filas)

    def test_una_tarifa_justo_sobre_el_umbral_es_por_mil(self):
        filas = [_fila("11001", "a", 2.0), _fila("11001", "b", 14.0)]
        verificar_unidad_coherente(filas)


class TestFilasQueNoCuentan:
    def test_ignora_las_tarifas_en_cero(self):
        """Un cero no está en ninguna unidad; no puede decidir la del archivo."""
        filas = [_fila("11001", "a", 9.66), _fila("11001", "b", 0)]
        verificar_unidad_coherente(filas)

    def test_ignora_las_tarifas_ilegibles(self):
        filas = [_fila("11001", "a", 9.66), _fila("11001", "b", "no-es-un-numero")]
        verificar_unidad_coherente(filas)
