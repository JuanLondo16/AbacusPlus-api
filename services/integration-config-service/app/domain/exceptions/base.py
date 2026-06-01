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


class ExternalServiceException(DomainException):
    def __init__(self, message: str):
        super().__init__(message=message, code="EXTERNAL_SERVICE_ERROR")


class ExternalAuthException(DomainException):
    def __init__(self, message: str):
        super().__init__(message=message, code="EXTERNAL_AUTH_ERROR")
