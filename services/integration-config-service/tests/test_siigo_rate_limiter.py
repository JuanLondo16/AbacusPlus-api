"""El diagnóstico fiscal no puede desbordar el cupo de peticiones de SIIGO.

Consulta SIIGO una vez por proveedor. Con el catálogo actual son unas cuarenta peticiones
seguidas; con trescientos terceros serían trescientas desde un único clic. SIIGO limita a 100
por minuto y responde 429 al superarlo, y ese error suma a la proporción por la que bloquea la
cuenta de la API.

Lo que se comprueba aquí es el equilibrio entre las dos cosas que importan: que un diagnóstico
pequeño no espere —la ráfaga lo absorbe— y que uno grande no salga de golpe.
"""

import time

from app.infrastructure.clients.siigo_rate_limiter import TokenBucketRateLimiter


class TestLaRafagaNoPenalizaElCasoNormal:
    def test_las_peticiones_de_la_rafaga_no_esperan(self):
        """Cuarenta consultas con el cupo de producción deben salir sin pausa."""
        limitador = TokenBucketRateLimiter(90)  # ráfaga = 45
        inicio = time.monotonic()
        for _ in range(40):
            limitador.acquire()
        assert time.monotonic() - inicio < 0.1

    def test_la_rafaga_por_defecto_es_la_mitad_del_cupo(self):
        assert TokenBucketRateLimiter(90).available == 45
        assert TokenBucketRateLimiter(10).available == 5

    def test_la_rafaga_se_puede_fijar(self):
        assert TokenBucketRateLimiter(90, burst=3).available == 3


class TestUnDiagnosticoGrandeSeReparte:
    def test_agotada_la_rafaga_la_siguiente_espera(self):
        """Con el cupo consumido, la petición extra no sale hasta que se repone un permiso."""
        # 60 por minuto = 1 por segundo. Ráfaga de 2 para que la prueba sea rápida.
        limitador = TokenBucketRateLimiter(60, burst=2)
        limitador.acquire()
        limitador.acquire()

        inicio = time.monotonic()
        limitador.acquire()
        transcurrido = time.monotonic() - inicio
        assert 0.5 < transcurrido < 1.6, f"esperó {transcurrido:.2f}s"

    def test_los_permisos_se_reponen_con_el_tiempo(self):
        limitador = TokenBucketRateLimiter(600, burst=1)  # 10 por segundo
        limitador.acquire()
        time.sleep(0.25)
        assert limitador.available >= 1

    def test_la_reposicion_no_supera_la_capacidad(self):
        """Estar parado un rato no acumula permisos para un pico posterior."""
        limitador = TokenBucketRateLimiter(600, burst=2)
        time.sleep(0.2)
        assert limitador.available == 2


class TestConfiguracion:
    def test_un_cupo_no_positivo_es_un_error(self):
        for invalido in (0, -1):
            try:
                TokenBucketRateLimiter(invalido)
            except ValueError:
                continue
            raise AssertionError(f"{invalido} debió rechazarse")
