"""Limitador de peticiones hacia SIIGO para el contraste de configuración fiscal.

POR QUÉ HACE FALTA AQUÍ
───────────────────────
El diagnóstico consulta SIIGO **una vez por proveedor** para comparar sus responsabilidades
fiscales. Con el catálogo actual del cliente son unas cuarenta peticiones seguidas; con un
catálogo de trescientos terceros serían trescientas, disparadas sin pausa desde un único clic.

SIIGO limita a 100 peticiones por minuto en producción —10 en empresas de prueba— y responde
`requests_limit` (429) al superarlo. Un 429 no solo es una petición perdida: suma a la
proporción de errores de la cuenta, y SIIGO bloquea el usuario de la API cuando esa proporción
se mantiene alta. Conviene no llegar a él en lugar de reaccionar cuando llega.

POR QUÉ TOKEN BUCKET Y NO UNA PAUSA FIJA
────────────────────────────────────────
Una pausa fija entre llamadas —0,6 s para no pasar de 100 por minuto— penaliza el caso normal:
las cuarenta peticiones de hoy caben de sobra en el cupo y tardarían veinticinco segundos sin
ninguna necesidad.

El bucket reparte permisos a ritmo constante pero admite una ráfaga inicial. Un diagnóstico
pequeño sale entero de la ráfaga y no espera nada; uno grande consume la ráfaga y a partir de
ahí avanza al ritmo permitido. El coste se paga solo cuando de verdad hay que pagarlo.

ALCANCE
───────
Vive en memoria del proceso, como el del xml-processor. Con una instancia es exacto; con
varias réplicas cada una llevaría su cuenta y el techo real sería N veces el configurado. Se
deja escrito para que, el día que se escale horizontalmente, la decisión sea consciente: el
limitador tendría que pasar a Redis, que el proyecto ya usa.
"""

import os
import threading
import time
from typing import Optional


class TokenBucketRateLimiter:
    """Reparte permisos a un ritmo constante, con capacidad para ráfagas acotadas."""

    def __init__(self, rate_per_minute: int, *, burst: Optional[int] = None):
        if rate_per_minute <= 0:
            raise ValueError("El límite de peticiones por minuto debe ser mayor que cero.")
        self._rate_per_second = rate_per_minute / 60.0
        # Ráfaga generosa a propósito: la mitad del cupo. Este limitador protege un diagnóstico
        # de solo lectura que se lanza a mano, no una cola que escribe asientos, así que el
        # riesgo de un pico moderado es bajo y la espera innecesaria sí se nota en pantalla.
        self._capacity = float(burst if burst is not None else max(1, rate_per_minute // 2))
        self._tokens = self._capacity
        self._updated_at = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Espera hasta tener permiso para una petición."""
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                espera = (1.0 - self._tokens) / self._rate_per_second
            # Fuera del cerrojo: retenerlo durante la espera serializaría a cualquier otra
            # petición que estuviera esperando su turno.
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
        """Permisos disponibles ahora mismo. Para diagnóstico y pruebas."""
        with self._lock:
            self._refill()
            return self._tokens


def _limite_configurado() -> int:
    """Peticiones por minuto. `SIIGO_MAX_REQUESTS_PER_MINUTE` permite bajarlo en pruebas.

    El valor por defecto es 90 y no 100: deja margen para las peticiones que el mismo proceso
    hace por otros motivos —autenticación, tipos de comprobante— dentro del mismo minuto.
    """
    try:
        valor = int(os.getenv("SIIGO_MAX_REQUESTS_PER_MINUTE", "90"))
    except ValueError:
        return 90
    return valor if valor > 0 else 90


#: Único para todo el proceso: el límite de SIIGO es por empresa, no por diagnóstico.
limitador_siigo = TokenBucketRateLimiter(_limite_configurado())
