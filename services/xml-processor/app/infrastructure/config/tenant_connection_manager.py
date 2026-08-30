import logging
import os
import re
import threading
from collections import OrderedDict

from sqlalchemy import NullPool, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.persistence.tenant_migrations import apply_tenant_migrations

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# Caché acotada de fábricas de sesión. Sin límite, cada cliente que entra deja su engine
# residente para siempre: con un puñado de clientes es irrelevante, pero el diseño de una
# base por cliente está pensado para crecer y la memoria crecería con él sin techo.
# Al desbordar se descarta el cliente menos usado recientemente y se liberan sus recursos.
_MAX_TENANTS_EN_CACHE = int(os.getenv("TENANT_ENGINE_CACHE_SIZE", "50"))
_session_factories: "OrderedDict[str, sessionmaker]" = OrderedDict()

# Clientes cuya base ya se migró en este proceso. Se lleva aparte de la caché de engines
# porque son cosas distintas: expulsar un engine por falta de espacio no significa que haya
# que volver a migrar esa base. Sin esta separación, un cliente que entra y sale de la caché
# repetiría las ~25 sentencias de migración en cada reconexión.
_tenants_migrados: set = set()

# Formato que produce el aprovisionamiento de tenants: minúsculas, dígitos y guion bajo.
_SLUG_PATTERN = re.compile(r"[a-z0-9_]+")


def _validated_slug(tenant_slug: str) -> str:
    """Valida el slug antes de interpolarlo en la URL de conexión.

    El slug llega de un claim del JWT. Aunque el token esté firmado y verificado, el slug
    termina concatenado en un DSN, así que un valor con caracteres de control o de sintaxis
    de URL podría alterar el destino de la conexión. Se restringe a minúsculas, dígitos y
    guiones bajos —el formato que produce el aprovisionamiento— como defensa en profundidad.
    """
    if not _SLUG_PATTERN.fullmatch(tenant_slug or ""):
        raise ValueError(f"Slug de tenant inválido: {tenant_slug!r}")
    return tenant_slug


def _build_url(tenant_slug: str) -> str:
    user = os.environ["DATABASE_USER"]
    password = os.environ["DATABASE_PASSWORD"]
    host = os.environ["DATABASE_HOST"]
    port = os.environ.get("DATABASE_PORT", "5432")
    slug = _validated_slug(tenant_slug)
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/abacus_t_{slug}"


def _desalojar_si_hace_falta() -> None:
    """Libera el engine del cliente menos usado cuando la caché se llena."""
    while len(_session_factories) > _MAX_TENANTS_EN_CACHE:
        slug, factory = _session_factories.popitem(last=False)
        try:
            factory.kw["bind"].dispose()
        except Exception as exc:  # liberar es best-effort: no debe tumbar la petición
            logger.warning("No se pudo liberar el engine del tenant %s: %s", slug, exc)
        logger.info(
            "Engine del tenant %s liberado por límite de caché (%d)",
            slug,
            _MAX_TENANTS_EN_CACHE,
        )


def get_session_for_tenant(tenant_slug: str) -> Session:
    """Devuelve una sesión contra la base del cliente indicado.

    Las migraciones se aplican una sola vez por cliente y por proceso. Antes se ejecutaban
    al crear el engine, que con la caché sin límite equivalía a lo mismo; ahora que la caché
    puede desalojar entradas, el registro se lleva aparte para no repetirlas.

    Las sentencias viven en `infrastructure/persistence/tenant_migrations.py`, que es el
    único lugar donde se declaran en todo el servicio.
    """
    with _lock:
        factory = _session_factories.get(tenant_slug)
        if factory is not None:
            # move_to_end mantiene el orden de uso, que es lo que hace útil el desalojo.
            _session_factories.move_to_end(tenant_slug)
        else:
            engine = create_engine(_build_url(tenant_slug), poolclass=NullPool)
            if tenant_slug not in _tenants_migrados:
                # strict=False: si una migración falla, se registra pero el cliente puede
                # seguir operando. Un servicio que no arranca por esto deja al cliente sin
                # sistema, y el aviso en el log permite corregirlo sin caída.
                apply_tenant_migrations(engine, create_tables=False, strict=False)
                _tenants_migrados.add(tenant_slug)
            factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            _session_factories[tenant_slug] = factory
            _desalojar_si_hace_falta()

    return factory()


def known_tenants() -> list:
    """Clientes con conexión ya establecida en este proceso.

    La usa el supervisor de la cola de contabilización (RF-05) para saber sobre qué bases
    debe buscar trabajo pendiente.

    **Qué NO es:** la lista de todos los clientes del sistema. Un cliente entra aquí cuando
    llega su primera petición, y la caché puede desalojarlo si hay muchos. Para la cola eso
    basta y no es casualidad: un trabajo solo existe si alguien lo encoló, y encolarlo exigió
    una petición de ese cliente, que es justo lo que lo registra.

    El arranque en frío —trabajos encolados antes de un reinicio, sin ningún usuario todavía
    conectado— NO se cubre aquí: lo cubre `all_tenant_slugs()`, que lee el catálogo de bases.
    El supervisor de la cola usa la unión de ambas.
    """
    with _lock:
        return list(_session_factories.keys())


def all_tenant_slugs() -> list:
    """Todos los clientes aprovisionados, leídos del catálogo de bases de PostgreSQL.

    Complementa a `known_tenants()`, que solo conoce a quien ya pidió algo **en este
    proceso**. Esa diferencia importa para la cola de contabilización (RF-05): tras un
    reinicio, los trabajos encolados antes de caer quedaban esperando a que alguien de ese
    cliente entrara a la aplicación. Un lote enviado al final del día y un despliegue esa
    misma noche dejaban los documentos sin contabilizar hasta la mañana siguiente, con el
    contador convencido de que ya iban camino de SIIGO.

    Se resuelve consultando `pg_database` en lugar de preguntar al auth-service: la lista de
    bases `abacus_t_*` ya es la lista de clientes aprovisionados, y así no se introduce un
    acoplamiento entre servicios para un dato que esta conexión ya tiene delante.

    Nunca lanza: si el catálogo no se puede consultar, el supervisor sigue con los clientes
    que ya conoce. Un fallo aquí debe degradar, no detener la cola.
    """
    user = os.environ.get("DATABASE_USER")
    password = os.environ.get("DATABASE_PASSWORD")
    host = os.environ.get("DATABASE_HOST")
    port = os.environ.get("DATABASE_PORT", "5432")
    admin_db = os.environ.get("DATABASE_NAME", "postgres")
    if not (user and password and host):
        return []

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{admin_db}"
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            # `left(...)` en vez de `LIKE 'abacus\_t\_%'`: el comodín `%` puede colisionar
            # con el marcador de parámetros de algunos drivers, y el guion bajo de `LIKE` es
            # a su vez un comodín que habría que escapar. Comparar el prefijo evita las dos
            # trampas y dice lo mismo de forma más directa.
            filas = conn.execute(
                text(
                    "SELECT datname FROM pg_database "
                    "WHERE left(datname, 9) = 'abacus_t_' AND NOT datistemplate"
                )
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo enumerar las bases de clientes: %s", exc)
        return []
    finally:
        engine.dispose()

    slugs = []
    for (datname,) in filas:
        slug = str(datname)[len("abacus_t_") :]
        # El slug vuelve a validarse aunque venga del propio catálogo: es lo que se
        # interpolará después en un DSN, y la regla es no confiar en el origen sino en el
        # formato.
        if _SLUG_PATTERN.fullmatch(slug):
            slugs.append(slug)
    return slugs
