"""RF-05: política de reintentos de la contabilización.

Decide una sola cosa: dado un fallo ya clasificado y el historial del trabajo, ¿se reintenta
solo, y cuándo?

Está aislado del worker a propósito. La política de reintentos es lo que más se va a ajustar
con la experiencia real —cuántos intentos, cuánto backoff, qué clases merecen reintento— y
tenerla en su propio módulo, sin dependencias de red ni de base de datos, significa que
ajustarla es cambiar reglas puras y que probarla no necesita ni SIIGO ni PostgreSQL.

La regla que no se negocia
--------------------------
**Un fallo de clase `UNCERTAIN` no se reintenta nunca automáticamente.** Da igual el número
de intentos disponibles: si no consta que SIIGO dejó de crear la factura, reintentar es
apostar contra la contabilidad del cliente. Esos trabajos salen de la cola hacia
reconciliación, que verifica antes de decidir.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.domain.value_objects.accounting_error import ErrorClass, is_auto_retryable
from app.infrastructure.config.accounting_settings import AccountingSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryDecision:
    """Qué hacer con un trabajo que acaba de fallar."""

    should_retry: bool
    #: Cuándo puede volver a intentarse. None si no se reintenta.
    next_attempt_at: Optional[datetime] = None
    #: Segundos de espera aplicados. Se audita: explica por qué un documento «no hace nada»
    #: durante cinco minutos, que de otro modo parece un cuelgue.
    backoff_seconds: float = 0.0
    #: Motivo de la decisión, en texto. Va al log y al historial del trabajo.
    reason: str = ""
    #: True si el trabajo debe salir de la cola hacia reconciliación humana.
    needs_reconciliation: bool = False


class RetryManager:
    """Aplica la política de reintentos a un fallo clasificado."""

    def __init__(self, settings: AccountingSettings):
        self.settings = settings

    def decide(
        self,
        *,
        error_class: str,
        attempt: int,
        max_attempts: int,
        now: Optional[datetime] = None,
    ) -> RetryDecision:
        """Decide el destino de un trabajo tras un intento fallido.

        `attempt` es el número del intento que acaba de fallar (el primero es 1). `max_attempts`
        viene del trabajo y no de la configuración global: se fijó al encolar, de modo que
        cambiar el máximo del sistema no revive trabajos que ya se dieron por agotados con la
        regla anterior.
        """
        ahora = now or datetime.now(timezone.utc)

        if error_class in (ErrorClass.UNCERTAIN, ErrorClass.DUPLICATE):
            # La regla que no se negocia. Ver el encabezado del módulo.
            return RetryDecision(
                should_retry=False,
                needs_reconciliation=True,
                reason=(
                    "No consta que SIIGO haya dejado de crear el comprobante. El reintento "
                    "automático queda descartado: hay que verificar en SIIGO antes de "
                    "volver a enviar."
                ),
            )

        if not is_auto_retryable(error_class):
            # Corregibles, de configuración y desconocidos. Repetir la misma petición con los
            # mismos datos daría el mismo resultado y solo gastaría cupo del límite por
            # minuto; hace falta que alguien cambie algo primero.
            return RetryDecision(
                should_retry=False,
                reason=(
                    "El fallo no se resuelve repitiendo la petición: requiere una corrección "
                    "antes de volver a enviar."
                ),
            )

        if attempt >= max_attempts:
            return RetryDecision(
                should_retry=False,
                reason=(
                    f"Se agotaron los {max_attempts} intentos automáticos. El documento "
                    "queda a la espera de un reintento manual."
                ),
            )

        espera = self.settings.backoff_for(attempt)
        return RetryDecision(
            should_retry=True,
            next_attempt_at=ahora + timedelta(seconds=espera),
            backoff_seconds=espera,
            reason=(
                f"Fallo temporal ({error_class}). Reintento {attempt + 1} de {max_attempts} "
                f"dentro de {int(espera)} s."
            ),
        )
