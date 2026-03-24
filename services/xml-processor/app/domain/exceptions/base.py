class DomainException(Exception):
    """Base exception for all domain errors."""

    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class EntityNotFoundException(DomainException):
    def __init__(self, entity: str, identifier: str):
        super().__init__(
            message=f"{entity} not found: {identifier}",
            code="NOT_FOUND",
        )


class DuplicateEntityException(DomainException):
    def __init__(self, entity: str, identifier: str):
        super().__init__(
            message=f"{entity} already exists: {identifier}",
            code="DUPLICATE",
        )


class ValidationException(DomainException):
    def __init__(self, message: str):
        super().__init__(message=message, code="VALIDATION_ERROR")


class AuthenticationException(DomainException):
    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message=message, code="AUTHENTICATION_ERROR")


class FileProcessingException(DomainException):
    def __init__(self, message: str):
        super().__init__(message=message, code="FILE_PROCESSING_ERROR")
