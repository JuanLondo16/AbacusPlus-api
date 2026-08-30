"""Freno de intentos de login.

El login era el único endpoint del sistema sin coste para quien lo llama: acepta correo y
contraseña, responde en milisegundos y no limitaba el número de intentos. Con el slug del
cliente en el subdominio y los correos corporativos siendo previsibles, probar contraseñas
contra una cuenta concreta era cuestión de tiempo de CPU.

El contador vive en Redis —ya presente en este servicio para los refresh tokens— y no en
memoria del proceso: con varias réplicas de auth-service detrás del gateway, un contador local
se dividiría entre ellas y el límite real sería el configurado multiplicado por el número de
réplicas.

Se cuentan **solo los intentos fallidos** y la clave se borra al autenticar correctamente, de
modo que un usuario legítimo que se equivoca un par de veces y acierta no arrastra penalización.

Si Redis no responde, se **deja pasar**. Es una decisión deliberada: este freno protege contra
un abuso, no es la comprobación de identidad —esa la sigue haciendo bcrypt sobre el hash—, y
convertir una caída de Redis en la imposibilidad de que nadie entre en la plataforma sería un
daño mayor y más probable que el ataque del que defiende.
"""

import logging
import os

import redis

from app.infrastructure.config.redis_client import get_redis

logger = logging.getLogger(__name__)

#: Intentos fallidos admitidos dentro de la ventana antes de empezar a rechazar.
MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "10"))

#: Duración de la ventana, en segundos. El bloqueo se levanta solo al expirar la clave.
WINDOW_SECONDS = int(os.getenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "300"))


def _key(scope: str, value: str) -> str:
    return f"login_fail:{scope}:{value.lower()}"


def is_locked(email: str, client_ip: str) -> bool:
    """True si el correo o la IP acumulan demasiados fallos recientes.

    Se vigilan los dos por separado porque cubren ataques distintos: la cuenta frena el
    intento de adivinar la contraseña de una persona concreta, y la IP frena el barrido de
    muchas cuentas con contraseñas comunes, que nunca llegaría al tope de ninguna de ellas.
    """
    try:
        client = get_redis()
        for scope, value in (("email", email), ("ip", client_ip)):
            if not value:
                continue
            attempts = client.get(_key(scope, value))
            if attempts is not None and int(attempts) >= MAX_ATTEMPTS:
                return True
        return False
    except (redis.RedisError, ValueError) as exc:
        logger.warning("Rate limit no disponible, se permite el intento: %s", exc)
        return False


def register_failure(email: str, client_ip: str) -> None:
    """Suma un fallo a la cuenta y a la IP, renovando la ventana en el primer fallo."""
    try:
        client = get_redis()
        pipe = client.pipeline()
        for scope, value in (("email", email), ("ip", client_ip)):
            if not value:
                continue
            key = _key(scope, value)
            pipe.incr(key)
            # `expire` con `nx` deja intacta la caducidad ya puesta: la ventana se cuenta desde
            # el primer fallo, así que un atacante no puede prolongarla indefinidamente ni
            # reiniciarla insistiendo.
            pipe.expire(key, WINDOW_SECONDS, nx=True)
        pipe.execute()
    except redis.RedisError as exc:
        logger.warning("No se pudo registrar el intento fallido: %s", exc)


def clear(email: str, client_ip: str) -> None:
    """Borra los contadores tras un login correcto."""
    try:
        client = get_redis()
        keys = [_key(s, v) for s, v in (("email", email), ("ip", client_ip)) if v]
        if keys:
            client.delete(*keys)
    except redis.RedisError as exc:
        logger.warning("No se pudieron limpiar los contadores de login: %s", exc)
