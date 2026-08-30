from typing import Optional


class DomainException(Exception):
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ValidationException(DomainException):
    def __init__(self, message: str):
        super().__init__(message=message, code="VALIDATION_ERROR")


class EntityNotFoundException(DomainException):
    def __init__(self, entity: str, identifier: str):
        super().__init__(
            message=f"{entity} not found: {identifier}",
            code="NOT_FOUND",
        )


class SiigoConnectionException(DomainException):
    def __init__(self, message: str):
        super().__init__(message=message, code="SIIGO_CONNECTION_ERROR")


class SiigoAuthenticationException(DomainException):
    def __init__(self, message: str):
        super().__init__(message=message, code="SIIGO_AUTHENTICATION_ERROR")


class SiigoApiException(DomainException):
    """Error devuelto por SIIGO conservando el código HTTP y los errores de su cuerpo.

    Existe porque para RF-05 no basta con saber que «falló»: hay que decidir si el envío es
    reintentable. `SiigoConnectionException` aplana todo a un texto y esa distinción se
    pierde, y sin ella un reintento automático puede duplicar una factura de compra —que en
    /v1/purchases no está protegida por idempotencia.

    `retryable` es deliberadamente conservador: solo se marcan como reintentables los fallos
    en los que SIIGO no llegó a procesar la petición (429 y 5xx explícitos). Un timeout o un
    error de red NO son reintentables aquí, porque la petición pudo haber llegado y creado
    la factura sin que nosotros viéramos la respuesta.
    """

    #: SIIGO limita a 100 peticiones por minuto y por empresa.
    TOO_MANY_REQUESTS = 429

    def __init__(
        self,
        message: str,
        # `Optional[...]` y no `int | None`: este servicio corre sobre Python 3.9, donde la
        # unión con `|` (PEP 604) todavía no existe y rompe el import del módulo entero.
        status_code: Optional[int] = None,
        errors: Optional[list] = None,
        retryable: bool = False,
    ):
        super().__init__(message=message, code="SIIGO_API_ERROR")
        self.status_code = status_code
        self.errors = errors or []
        self.retryable = retryable

    @property
    def error_codes(self) -> list[str]:
        """Códigos de error de SIIGO (`duplicated_document`, `parameter_required`, …)."""
        return [e.get("Code") for e in self.errors if isinstance(e, dict) and e.get("Code")]

    @property
    def is_duplicate(self) -> bool:
        """True si SIIGO afirma que el comprobante ya existe.

        Es el único caso en que un 400/409 significa «la factura ya está en SIIGO» y no
        «los datos están mal», así que el documento no debe volver a enviarse: debe
        reconciliarse.
        """
        return "duplicated_document" in self.error_codes

    #: Códigos HTTP en los que consta que SIIGO rechazó la petición ANTES de tocar la
    #: contabilidad. Es la lista que autoriza a volver a enviar un documento, así que solo
    #: entra aquí un código cuyo significado no admita una segunda lectura.
    #:
    #: 4xx de validación y de autorización: SIIGO valida la petición antes de procesarla, y
    #: un rechazo en esa fase no crea nada. 429 es un rechazo en la puerta, por cupo. 503 es
    #: «no atendí la petición», que SIIGO documenta como servicio no disponible.
    SAFE_STATUS_CODES = frozenset({400, 401, 403, 404, 422, 429, 503})

    @property
    def siigo_did_not_create(self) -> bool:
        """True cuando consta que SIIGO **no** llegó a crear el comprobante.

        Es una pregunta distinta de `retryable`, y confundirlas cuesta caro. `retryable`
        responde «¿tiene sentido repetir esta misma petición automáticamente?». Esta
        responde «¿es seguro volver a enviar el documento después de corregirlo?», que es lo
        que decide si el documento puede reenviarse o si hay que verificar en SIIGO primero.

        Un 400 por datos inválidos no es `retryable` —repetirlo sin cambiar nada fallaría
        igual— pero sí es seguro reenviarlo tras corregir: SIIGO lo rechazó sin crear nada.

        **Los 5xx quedan FUERA, y ésta es la parte que importa.** La versión anterior de esta
        propiedad devolvía True para todo el rango 400–599, lo que declaraba seguro reenviar
        tras un 500, un 502 o un 504. No lo es: un 5xx de SIIGO es indistinguible entre
        «falló antes de crear el comprobante» y «lo creó y falló al responder», y
        /v1/purchases no admite `Idempotency-Key` para deshacer esa ambigüedad. Con la
        versión anterior, un 500 durante un pico de uso de SIIGO liberaba el documento para
        reenvío y creaba un segundo asiento contable real en la contabilidad del cliente.
        Ese daño no se deshace desde aquí.

        También quedan fuera el duplicado —ahí el comprobante sí existe— y los casos sin
        `status_code` (timeout, red, respuesta ilegible), donde no se sabe nada.

        408 (`request_timeout`) queda fuera igualmente: es SIIGO diciendo que la petición
        tardó demasiado, no que la descartara.
        """
        if self.is_duplicate or self.status_code is None:
            return False
        return self.status_code in self.SAFE_STATUS_CODES
