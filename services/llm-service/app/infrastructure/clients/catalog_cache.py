"""Caché con vencimiento de los catálogos por empresa (plan de cuentas y centros de costo).

**Por qué existe.** Asignar cuentas a un documento empieza pidiendo el plan de cuentas
completo y los centros de costo al integration-config-service. Son catálogos de empresa: los
mismos para todos los documentos del mismo cliente y prácticamente inmutables entre
importaciones. Al causar un lote se pedían íntegros una vez por documento —cientos de filas
cada vez— y a continuación se recalculaba sobre ellos la misma lista de cuentas candidatas.

**Aislamiento entre clientes.** La clave es el `tenant_slug` del token ya validado, nunca el
token ni una cabecera del cliente. Dos empresas jamás comparten una entrada, y un token
manipulado no puede alcanzar la entrada de otra: el slug sale de la firma del JWT, que se
verifica antes de llegar aquí.

**Frescura.** El TTL es corto y configurable (`CATALOG_CACHE_TTL_SECONDS`, 120 s por
defecto). Es la ventana máxima durante la cual una importación de plan de cuentas puede no
verse reflejada en una sugerencia; ponerlo en `0` desactiva la caché por completo, que es lo
que hay que hacer mientras se depura una importación.

**Qué NO se guarda aquí.** Solo catálogos de configuración. Ningún documento, ninguna línea,
ningún dato del usuario ni respuesta del modelo: esos son por documento y cachearlos sería
devolver el trabajo de otro.
"""

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


def _ttl() -> float:
    """TTL en segundos, leído en cada consulta para poder cambiarlo sin reconstruir imagen."""
    try:
        return max(0.0, float(os.getenv("CATALOG_CACHE_TTL_SECONDS", "120")))
    except ValueError:
        logger.warning("CATALOG_CACHE_TTL_SECONDS no es un número; se usa 120 s")
        return 120.0


#: Tope de entradas vivas. Cada entrada es un tenant × catálogo; el tope evita que un
#: despliegue con muchos clientes acumule catálogos indefinidamente en memoria. Al llenarse
#: se descarta la entrada más antigua, que es la que más probablemente ya venció.
_MAX_ENTRIES = 256


class _TenantCatalogCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], tuple[float, Any]] = {}
        # Un lock por clave: dos peticiones del mismo cliente que fallen la caché a la vez
        # deben resultar en **una** llamada al servicio de catálogos, no en dos. Sin esto, un
        # lote de 60 documentos arrancando en paralelo pediría el plan de cuentas 60 veces.
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def get_or_load(
        self,
        tenant_slug: str,
        catalogo: str,
        loader: Callable[[], Awaitable[Any]],
    ) -> Any:
        ttl = _ttl()
        if ttl <= 0 or not tenant_slug:
            # Sin TTL no hay caché; sin tenant identificado tampoco, porque no habría con qué
            # separar una empresa de otra y compartir catálogos entre clientes es inaceptable.
            return await loader()

        clave = (tenant_slug, catalogo)
        ahora = time.monotonic()

        entrada = self._entries.get(clave)
        if entrada is not None and entrada[0] > ahora:
            return entrada[1]

        async with self._guard:
            lock = self._locks.setdefault(clave, asyncio.Lock())

        async with lock:
            # Segunda comprobación: mientras esperábamos el lock, otra corutina pudo cargarlo.
            entrada = self._entries.get(clave)
            ahora = time.monotonic()
            if entrada is not None and entrada[0] > ahora:
                return entrada[1]

            valor = await loader()

            # Un catálogo vacío no se cachea. Los clientes de este servicio son best-effort y
            # devuelven `[]` cuando el servicio de catálogos no responde: guardar ese vacío
            # convertiría una caída momentánea en dos minutos de sugerencias sin plan de
            # cuentas, que es peor que repetir la llamada.
            if valor:
                if len(self._entries) >= _MAX_ENTRIES:
                    mas_antigua = min(self._entries, key=lambda k: self._entries[k][0])
                    self._entries.pop(mas_antigua, None)
                    self._locks.pop(mas_antigua, None)
                self._entries[clave] = (ahora + ttl, valor)
            return valor

    def invalidate(self, tenant_slug: str, catalogo: Optional[str] = None) -> None:
        """Descarta lo cacheado de una empresa (o de uno de sus catálogos)."""
        for clave in list(self._entries):
            if clave[0] == tenant_slug and (catalogo is None or clave[1] == catalogo):
                self._entries.pop(clave, None)
                self._locks.pop(clave, None)


#: Instancia única del proceso. Es estado compartido a propósito: su valor está justamente en
#: que todas las peticiones del mismo cliente lo compartan.
catalog_cache = _TenantCatalogCache()
