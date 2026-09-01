"""RF-05: parámetros operativos de la contabilización, todos configurables.

Ningún número de esta funcionalidad puede vivir incrustado en la lógica. La razón no es
estética: la estrategia de cola depende de límites de SIIGO que todavía no están confirmados
contra el ambiente real (concurrencia tolerada, latencia de indexación, comportamiento ante
peticiones simultáneas). Cuando esas pruebas den su resultado, ajustar la estrategia debe
ser cambiar una variable de entorno y reiniciar, no reabrir el código.

Hay además una razón de ambiente: SIIGO limita a **10 peticiones por minuto en empresas de
prueba y 100 en producción**. Con el valor incrustado, el mismo binario no puede correr
correctamente en los dos sitios.

Los valores por defecto son deliberadamente conservadores —concurrencia 1, que equivale al
comportamiento secuencial actual—. Subirlos es una decisión que debe apoyarse en las pruebas
contra SIIGO, no en una suposición escrita aquí.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int, *, minimo: int = 0) -> int:
    """Lee un entero del entorno sin dejar que un valor inválido tumbe el arranque.

    Un typo en una variable de entorno no debe impedir que el servicio levante: se registra
    y se usa el valor por defecto, que siempre es seguro. Fallar aquí dejaría el servicio
    caído por un carácter, y el modo degradado (defaults conservadores) es preferible.
    """
    crudo = os.getenv(name)
    if crudo is None or crudo.strip() == "":
        return default
    try:
        valor = int(crudo)
    except ValueError:
        logger.warning(
            "RF-05: %s='%s' no es un entero; se usa el valor por defecto %s",
            name,
            crudo,
            default,
        )
        return default
    if valor < minimo:
        logger.warning(
            "RF-05: %s=%s está por debajo del mínimo %s; se usa el mínimo",
            name,
            valor,
            minimo,
        )
        return minimo
    return valor


def _float_env(name: str, default: float, *, minimo: float = 0.0) -> float:
    crudo = os.getenv(name)
    if crudo is None or crudo.strip() == "":
        return default
    try:
        valor = float(crudo)
    except ValueError:
        logger.warning(
            "RF-05: %s='%s' no es un número; se usa el valor por defecto %s",
            name,
            crudo,
            default,
        )
        return default
    return max(valor, minimo)


@dataclass(frozen=True)
class AccountingSettings:
    """Configuración efectiva de la cola de contabilización."""

    #: Trabajadores que pueden llamar a SIIGO a la vez.
    #:
    #: Arranca en 1 —comportamiento secuencial— a propósito. SIIGO documenta un límite de
    #: peticiones por minuto, pero NO documenta ningún límite de concurrencia, y suponer que
    #: tolera N simultáneas sin haberlo comprobado es la clase de suposición que produce
    #: respuestas ambiguas, y una respuesta ambigua en /v1/purchases es un duplicado
    #: potencial. Se sube cuando las pruebas contra SIIGO lo respalden.
    max_concurrency: int = 1

    #: Peticiones por minuto contra SIIGO. 100 en producción, 10 en empresas de prueba.
    rate_limit_per_minute: int = 100

    #: Intentos automáticos de un error reintentable, incluido el primero.
    max_attempts: int = 5

    #: Backoff exponencial: base ** intento, acotado por el máximo.
    backoff_base_seconds: float = 2.0
    backoff_max_seconds: float = 300.0

    #: SIIGO recomienda esperar 120 s o más antes de cortar la creación de un comprobante:
    #: en picos de uso algunas transacciones tardan más que los <2 s habituales. Cortar antes
    #: no evita que la factura se cree, solo impide que veamos el identificador — que es
    #: precisamente el escenario que obliga a reconciliar.
    siigo_timeout_seconds: float = 120.0

    #: Margen adicional del salto de red interno hasta siigo-service. Debe ser mayor que el
    #: timeout de SIIGO para que sea SIIGO, y no nosotros, quien decida el desenlace.
    internal_timeout_margin_seconds: float = 30.0

    #: Cada cuánto la interfaz consulta el progreso de un lote encolado.
    poll_interval_seconds: float = 5.0

    #: Espera antes de consultar a SIIGO si una factura de desenlace incierto existe.
    #:
    #: SIIGO no documenta la latencia entre la creación y la visibilidad en GET
    #: /v1/purchases. Consultar demasiado pronto puede devolver «no existe» sobre una factura
    #: que sí se creó, y ese falso negativo autorizaría un reenvío duplicado. El valor real
    #: sale de la prueba T6. Hasta entonces, un margen amplio.
    reconcile_delay_seconds: float = 10.0

    #: Documentos por envío. Con cola ya no acota la duración de la petición HTTP —encolar es
    #: inmediato—, solo evita que un clic accidental encole el histórico entero.
    batch_max_size: int = 200

    #: Segundos tras los cuales un trabajo tomado por un worker que murió se considera
    #: huérfano y puede rescatarse. Debe superar con holgura al timeout de SIIGO.
    stale_job_seconds: int = 900

    @classmethod
    def from_env(cls) -> "AccountingSettings":
        return cls(
            max_concurrency=_int_env("ACCOUNTING_MAX_CONCURRENCY", 1, minimo=1),
            rate_limit_per_minute=_int_env("ACCOUNTING_RATE_LIMIT_PER_MINUTE", 100, minimo=1),
            max_attempts=_int_env("ACCOUNTING_MAX_ATTEMPTS", 5, minimo=1),
            backoff_base_seconds=_float_env("ACCOUNTING_BACKOFF_BASE_SECONDS", 2.0, minimo=1.0),
            backoff_max_seconds=_float_env("ACCOUNTING_BACKOFF_MAX_SECONDS", 300.0, minimo=1.0),
            siigo_timeout_seconds=_float_env("ACCOUNTING_SIIGO_TIMEOUT_SECONDS", 120.0, minimo=1.0),
            internal_timeout_margin_seconds=_float_env(
                "ACCOUNTING_INTERNAL_TIMEOUT_MARGIN_SECONDS", 30.0, minimo=0.0
            ),
            poll_interval_seconds=_float_env("ACCOUNTING_POLL_INTERVAL_SECONDS", 5.0, minimo=0.5),
            reconcile_delay_seconds=_float_env(
                "ACCOUNTING_RECONCILE_DELAY_SECONDS", 10.0, minimo=0.0
            ),
            batch_max_size=_int_env("ACCOUNTING_BATCH_MAX_SIZE", 200, minimo=1),
            stale_job_seconds=_int_env("ACCOUNTING_STALE_JOB_SECONDS", 900, minimo=60),
        )

    @property
    def client_timeout_seconds(self) -> float:
        """Timeout del salto interno: el de SIIGO más el margen de red."""
        return self.siigo_timeout_seconds + self.internal_timeout_margin_seconds

    def backoff_for(self, attempt: int) -> float:
        """Espera antes del intento `attempt` (1 = primer reintento), con techo.

        Exponencial porque es lo que SIIGO recomienda explícitamente ante `requests_limit`:
        reintentar a ritmo fijo contra un límite por minuto reproduce el 429 indefinidamente
        y, sostenido, alimenta la proporción de errores de la cuenta.
        """
        if attempt <= 0:
            return 0.0
        espera = self.backoff_base_seconds**attempt
        return min(espera, self.backoff_max_seconds)


def get_accounting_settings() -> AccountingSettings:
    """Configuración vigente. Se lee del entorno en cada llamada a propósito.

    No se cachea en un singleton para que un cambio de configuración surta efecto con un
    reinicio del proceso y no con un redespliegue, y para que los tests puedan alterar el
    entorno sin arrastrar estado entre casos.
    """
    return AccountingSettings.from_env()
