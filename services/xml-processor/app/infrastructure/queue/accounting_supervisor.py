"""RF-05: supervisor que mantiene viva la cola de contabilización de cada cliente.

El sistema es multi-cliente: cada uno tiene su propia base y su propia cola. El supervisor
recorre los clientes conocidos y da a cada uno una pasada de sus trabajos pendientes.

Por qué una pasada por ciclo y no un pool permanente por cliente
-----------------------------------------------------------------
Un pool de hilos por cliente escala con el número de clientes, no con el trabajo: cien
clientes en calma tendrían cien pools despiertos sin nada que hacer. El supervisor mantiene
un único pool y lo reutiliza cliente a cliente, así que el coste sigue al trabajo real.

Sobre el límite de peticiones a SIIGO
--------------------------------------
El limitador de tasa se comparte entre todos los clientes de este proceso. Es más estricto
de lo necesario —el cupo de SIIGO es por empresa, así que dos clientes distintos no compiten
entre sí— y esa severidad es deliberada mientras la concurrencia real no esté medida contra
el ambiente de SIIGO. Pasar a un limitador por cliente es un cambio contenido, y el momento
de hacerlo es cuando las pruebas digan qué tolera SIIGO de verdad.
"""

import asyncio
import logging
import time

from app.application.services.accounting_queue import AccountingQueueService  # noqa: F401
from app.infrastructure.config.accounting_settings import get_accounting_settings
from app.infrastructure.config.tenant_connection_manager import (
    all_tenant_slugs,
    get_session_for_tenant,
    known_tenants,
)
from app.infrastructure.persistence.repositories.accounting_job_repository import (
    AccountingJobRepository,
)
from app.infrastructure.queue.accounting_worker import AccountingWorkerPool

logger = logging.getLogger(__name__)


#: Cada cuánto se vuelve a leer el catálogo de clientes, en segundos.
#:
#: No se consulta en cada ciclo —el supervisor despierta cada pocos segundos— porque la
#: lista de clientes cambia con el aprovisionamiento, no con el minuto. Un minuto de retraso
#: en ver un cliente nuevo es irrelevante; consultar `pg_database` doce veces por minuto,
#: para siempre, no lo es.
_INTERVALO_DESCUBRIMIENTO_SEGUNDOS = 60.0

#: Última lista descubierta y cuándo se descubrió.
_cache_clientes: tuple = ((), 0.0)


def _clientes_a_revisar() -> list:
    """Clientes cuya cola hay que revisar en este ciclo.

    Es la unión de dos fuentes, y ninguna basta sola:

    - `known_tenants()` — los que ya pidieron algo en este proceso. Inmediato, pero vacío
      tras un reinicio.
    - `all_tenant_slugs()` — los aprovisionados, leídos del catálogo de bases. Cubre el
      arranque en frío, que es el hueco que de verdad importa: un lote encolado antes de un
      despliegue quedaba esperando a que alguien de ese cliente entrara a la aplicación, y
      si nadie entraba hasta el día siguiente, los documentos no se contabilizaban en toda
      la noche mientras el contador los daba por enviados.

    Si el catálogo falla, se sigue con los conocidos: degradar es aceptable, parar no.
    """
    global _cache_clientes
    descubiertos, momento = _cache_clientes
    ahora = time.monotonic()
    if ahora - momento >= _INTERVALO_DESCUBRIMIENTO_SEGUNDOS:
        nuevos = all_tenant_slugs()
        if nuevos:
            descubiertos = tuple(nuevos)
        _cache_clientes = (descubiertos, ahora)

    # `dict.fromkeys` deduplica conservando el orden: primero los que ya están conectados,
    # que son los que con más probabilidad tienen trabajo reciente.
    return list(dict.fromkeys(list(known_tenants()) + list(descubiertos)))


def _pool_para(tenant_slug: str) -> AccountingWorkerPool:
    """Arma el pool de un cliente concreto.

    El caso de uso se construye con el mismo constructor que usa el endpoint, en modo
    interno: un documento se contabiliza igual venga del botón o de la cola. Tener dos
    caminos capaces de divergir en una operación que crea asientos contables reales es
    exactamente el tipo de duplicación que acaba produciendo facturas mal formadas.
    """
    from app.dependencies import build_account_document_use_case

    return AccountingWorkerPool(
        session_factory=lambda: get_session_for_tenant(tenant_slug),
        job_repo_factory=AccountingJobRepository,
        use_case_factory=lambda session: build_account_document_use_case(
            session, raw_token="", tenant_slug=tenant_slug
        ),
    )


async def accounting_queue_supervisor() -> None:
    """Bucle de fondo que vacía las colas de contabilización de todos los clientes.

    Cada pasada se hace en un hilo aparte (`asyncio.to_thread`) porque el trabajo es
    bloqueante de principio a fin: consultas a la base y una llamada HTTP a SIIGO que puede
    tardar hasta dos minutos. Ejecutarlo en el bucle de eventos congelaría toda la API
    durante ese tiempo.

    Ningún fallo de un cliente detiene a los demás ni mata el supervisor: una excepción aquí
    dejaría todas las colas paradas sin que nada lo indicara, que es la peor forma de fallar
    para un componente cuya avería no se nota hasta que alguien pregunta por qué un
    documento lleva días sin contabilizarse.
    """
    settings = get_accounting_settings()
    logger.info(
        "RF-05: supervisor de contabilización iniciado (concurrencia=%s, %s peticiones/min)",
        settings.max_concurrency,
        settings.rate_limit_per_minute,
    )

    while True:
        try:
            for tenant_slug in _clientes_a_revisar():
                try:
                    procesados = await asyncio.to_thread(_drenar, tenant_slug)
                    if procesados:
                        logger.info(
                            "RF-05: %s trabajo(s) de contabilización procesados para %s",
                            procesados,
                            tenant_slug,
                        )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "RF-05: fallo al procesar la cola de contabilización de %s",
                        tenant_slug,
                    )
        except asyncio.CancelledError:
            logger.info("RF-05: supervisor de contabilización detenido")
            raise
        except Exception:  # noqa: BLE001
            logger.exception("RF-05: fallo inesperado en el supervisor de contabilización")

        await asyncio.sleep(get_accounting_settings().poll_interval_seconds)


def _drenar(tenant_slug: str) -> int:
    """Una pasada sobre la cola de un cliente. Devuelve cuántos trabajos procesó.

    Se acota a `batch_max_size` trabajos por pasada para que ningún cliente monopolice el
    supervisor: con una cola muy larga, sin este tope los demás clientes no verían avanzar
    la suya hasta que el primero terminara del todo.
    """
    settings = get_accounting_settings()
    pool = _pool_para(tenant_slug)
    return pool.drain(max_jobs=settings.batch_max_size, worker_id=f"sup-{tenant_slug}")
