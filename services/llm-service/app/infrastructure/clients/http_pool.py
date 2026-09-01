"""Pool de conexiones HTTP compartido para las llamadas entre servicios.

Cada cliente de este servicio abría un `httpx.AsyncClient` nuevo por llamada, dentro de un
`async with`. Eso significa montar y tirar la conexión TCP en cada petición: al asignar
cuentas a un lote de documentos, la misma conexión al integration-config-service se
establecía y se cerraba una vez por documento y por catálogo.

Un único cliente por proceso mantiene las conexiones vivas (keep-alive) y las reparte entre
las corutinas, que es justo lo que hace falta cuando el lote se procesa en paralelo. `httpx`
es seguro para uso concurrente desde varias tareas del mismo bucle de eventos.

El cliente **no** lleva cabeceras por defecto: las credenciales viajan por petición, porque
son del usuario que la originó y no del proceso. Compartir el transporte no es compartir la
identidad.
"""

import asyncio
from typing import Optional

import httpx

#: Límites del pool. `max_connections` acota cuántas conexiones simultáneas puede abrir este
#: servicio hacia el resto — el freno real a la concurrencia es el semáforo del lote, este es
#: la red de seguridad para que un pico no agote descriptores de fichero.
_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)

_client: Optional[httpx.AsyncClient] = None
_lock = asyncio.Lock()


async def get_client() -> httpx.AsyncClient:
    """Cliente HTTP compartido del proceso, creado la primera vez que se pide.

    La creación va bajo `lock` para que dos corutinas que arranquen a la vez no dejen un
    cliente huérfano —el que perdiera la carrera quedaría abierto y sin nadie que lo cierre—.
    """
    global _client
    if _client is None or _client.is_closed:
        async with _lock:
            if _client is None or _client.is_closed:
                _client = httpx.AsyncClient(limits=_LIMITS)
    return _client


async def close_client() -> None:
    """Cierra el pool al apagar el servicio, liberando las conexiones en curso."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
