"""RF-05: limitador de peticiones hacia SIIGO.

SIIGO limita a **100 peticiones por minuto en producción y 10 en empresas de prueba**, por
empresa, y responde `requests_limit` (429) al superarlo. Su documentación recomienda
explícitamente backoff exponencial ante ese error.

Reaccionar al 429 no basta como única estrategia. Un 429 es una petición gastada que además
suma a la proporción de errores de la cuenta, y hay un motivo por el que conviene no
llegar a él: en `/v1/purchases` cada petición es un intento de crear una factura, así que
cuantas menos peticiones inútiles salgan, menos ocasiones hay de que una se quede a medias
y deje un desenlace ambiguo. El limitador evita el 429 en lugar de esperar a recibirlo; el
backoff sigue existiendo para el que se cuele.

Algoritmo: **token bucket**. Se eligió frente a una ventana fija por una razón concreta:
con ventana fija, sesenta envíos a las 10:00:59 y otros sesenta a las 10:01:01 respetan la
ventana pero le meten a SIIGO 120 peticiones en dos segundos. El bucket reparte el cupo de
forma continua y no admite ese pico de borde.

Alcance
-------
Vive en memoria del proceso. Con una sola instancia del xml-processor es exacto. Con varias
réplicas, cada una llevaría su cuenta y el techo real sería N veces el configurado — en ese
escenario el limitador debe pasar a Redis, que el proyecto ya utiliza. Se documenta aquí
para que la decisión sea consciente y no una sorpresa el día que se escale horizontalmente.
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Reparte permisos a un ritmo constante, con capacidad para ráfagas acotadas."""

    def __init__(self, rate_per_minute: int, *, burst: Optional[int] = None):
        if rate_per_minute <= 0:
            raise ValueError("El límite de peticiones por minuto debe ser mayor que cero.")
        self._rate_per_second = rate_per_minute / 60.0
        # La capacidad por defecto es un 10% del cupo por minuto: permite una pequeña ráfaga
        # al arrancar un lote sin acercarse al límite. Una capacidad igual al cupo entero
        # dejaría salir 100 peticiones de golpe en el primer segundo, que es exactamente el
        # pico que este componente existe para evitar.
        self._capacity = float(burst if burst is not None else max(1, rate_per_minute // 10))
        self._tokens = self._capacity
        self._updated_at = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """Espera hasta tener permiso para una petición. False si venció el `timeout`.

        Bloquea el hilo llamante a propósito: el worker no tiene nada útil que hacer mientras
        espera su turno, y una espera explícita es más fácil de razonar —y de observar en un
        log— que una cola de callbacks.
        """
        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                faltan = 1.0 - self._tokens
                espera = faltan / self._rate_per_second

            if deadline is not None:
                restante = deadline - time.monotonic()
                if restante <= 0:
                    return False
                espera = min(espera, restante)

            # Se duerme fuera del cerrojo: retenerlo durante la espera serializaría a todos
            # los workers contra el más lento y anularía la concurrencia que se configuró.
            time.sleep(max(espera, 0.01))

    def _refill(self) -> None:
        ahora = time.monotonic()
        transcurrido = ahora - self._updated_at
        if transcurrido <= 0:
            return
        self._tokens = min(self._capacity, self._tokens + transcurrido * self._rate_per_second)
        self._updated_at = ahora

    @property
    def available(self) -> float:
        """Permisos disponibles ahora mismo. Para diagnóstico."""
        with self._lock:
            self._refill()
            return self._tokens
