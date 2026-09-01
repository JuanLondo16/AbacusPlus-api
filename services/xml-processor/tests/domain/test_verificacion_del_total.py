"""Contabilizar por un importe distinto al facturado no puede quedar en verde.

El defecto
----------
Ante `invalid_total_payments`, el sistema reenvía una vez con la cifra que SIIGO dice
esperar. La lógica de *por qué* reenviar es correcta —es un rechazo previo a la escritura, no
hay comprobante que duplicar—, pero **la cifra que devuelve SIIGO se calcula a partir de los
ítems que nosotros enviamos**. Si una línea está mal extraída, SIIGO responde el total
coherente con esa línea mal extraída, y el reenvío lo acepta.

El documento queda en CONTABILIZADO, sin advertencia, por un importe distinto al que la DIAN
declara. Un error de extracción se convierte en una contabilización limpia, que es la peor
forma de fallar: no hay nada que revisar porque nada parece roto.

Qué se corrige
--------------
Se compara el total que SIIGO informa contra `documents.total`. El documento se contabiliza
igual —la factura ya existe en SIIGO y nada puede deshacerla— pero la diferencia **queda
registrada y visible**. Es la diferencia entre un error silencioso y uno que alguien puede
encontrar.
"""

from app.domain.services.total_verification import (
    TOLERANCIA_DE_REDONDEO,
    VerificacionDelTotal,
    verificar_total_contabilizado,
)


class TestCuandoElTotalCoincide:
    def test_un_total_identico_no_produce_ninguna_alerta(self):
        v = verificar_total_contabilizado(total_siigo=83800.0, total_dian=83800.0)
        assert v.coincide is True
        assert v.diferencia == 0.0
        assert v.mensaje is None

    def test_una_diferencia_de_centimos_es_redondeo_y_no_alerta(self):
        """La DIAN redondea sus totales a peso: nueve de los 45 documentos del cliente
        traen `PayableRoundingAmount` distinto de cero. Una diferencia por debajo del peso
        no es un descuadre que el contador deba revisar."""
        v = verificar_total_contabilizado(total_siigo=83800.40, total_dian=83800.0)
        assert v.coincide is True
        assert abs(v.diferencia) < TOLERANCIA_DE_REDONDEO


class TestCuandoElTotalNoCoincide:
    def test_una_diferencia_real_se_marca(self):
        v = verificar_total_contabilizado(total_siigo=83301.0, total_dian=83800.0)
        assert v.coincide is False
        assert round(v.diferencia, 2) == -499.0

    def test_el_mensaje_nombra_las_dos_cifras(self):
        """El contador tiene que poder comparar sin abrir SIIGO."""
        v = verificar_total_contabilizado(total_siigo=83301.0, total_dian=83800.0)
        assert "83301" in v.mensaje.replace(".", "").replace(",", "")
        assert "83800" in v.mensaje.replace(".", "").replace(",", "")

    def test_el_mensaje_dice_que_la_factura_ya_existe_en_siigo(self):
        """No es un error que se pueda reintentar: el comprobante está creado. El mensaje
        debe dirigir a verificar, no a reenviar — reenviar duplicaría un asiento real."""
        v = verificar_total_contabilizado(total_siigo=83301.0, total_dian=83800.0)
        assert "SIIGO" in v.mensaje

    def test_detecta_tambien_cuando_siigo_contabiliza_de_mas(self):
        v = verificar_total_contabilizado(total_siigo=90000.0, total_dian=83800.0)
        assert v.coincide is False
        assert v.diferencia > 0


class TestCuandoNoHayConQueComparar:
    def test_sin_total_de_siigo_no_se_puede_afirmar_nada(self):
        """No se inventa una coincidencia: se declara que no se pudo comprobar.

        Dar por bueno lo que no se ha comprobado es exactamente lo que producía el defecto.
        """
        v = verificar_total_contabilizado(total_siigo=None, total_dian=83800.0)
        assert v.comprobado is False
        assert v.coincide is None

    def test_sin_total_de_la_dian_tampoco(self):
        v = verificar_total_contabilizado(total_siigo=83800.0, total_dian=None)
        assert v.comprobado is False
        assert v.coincide is None

    def test_un_total_ilegible_no_estalla(self):
        v = verificar_total_contabilizado(total_siigo="no-es-un-numero", total_dian=83800.0)
        assert v.comprobado is False


class TestLecturaDelTotalEnLaRespuestaDeSiigo:
    def test_extrae_el_total_del_cuerpo(self):
        from app.domain.services.total_verification import total_de_la_respuesta

        assert total_de_la_respuesta({"id": "abc", "total": 83800.0}) == 83800.0

    def test_admite_el_total_como_texto(self):
        from app.domain.services.total_verification import total_de_la_respuesta

        assert total_de_la_respuesta({"total": "83800.00"}) == 83800.0

    def test_lee_el_total_dentro_de_siigo_response(self):
        """El cuerpo que devuelve el siigo-service ENVUELVE la respuesta de SIIGO.

        `{"siigo_id": …, "siigo_name": …, "siigo_response": {"total": …}}`. Buscar `total`
        solo en la raíz devolvía None siempre, y `documents.siigo_total` quedaba vacío en
        cada documento — que es justo el hueco que esta columna venía a cerrar.
        """
        from app.domain.services.total_verification import total_de_la_respuesta

        cuerpo = {
            "siigo_id": "6d9b4440-9e72-470a-b5b2-2310c3e52f97",
            "siigo_name": "FC-1-202608026",
            "siigo_response": {"id": "6d9b…", "total": 67303.27},
        }
        assert total_de_la_respuesta(cuerpo) == 67303.27

    def test_la_raiz_sigue_funcionando_si_no_viene_envuelto(self):
        from app.domain.services.total_verification import total_de_la_respuesta

        assert total_de_la_respuesta({"total": 83800.0}) == 83800.0

    def test_sin_total_devuelve_nada(self):
        from app.domain.services.total_verification import total_de_la_respuesta

        assert total_de_la_respuesta({"id": "abc"}) is None
        assert total_de_la_respuesta(None) is None
        assert total_de_la_respuesta("no es un objeto") is None


class TestLaVerificacionEsUnDatoTransportable:
    def test_es_un_objeto_con_los_campos_que_se_persisten(self):
        v = verificar_total_contabilizado(total_siigo=83301.0, total_dian=83800.0)
        assert isinstance(v, VerificacionDelTotal)
        assert v.total_siigo == 83301.0
        assert v.total_dian == 83800.0
