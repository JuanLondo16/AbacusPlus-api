class DomainException(Exception):
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ValidationException(DomainException):
    def __init__(self, message: str):
        super().__init__(message=message, code="VALIDATION_ERROR")


class SessionNotFoundException(DomainException):
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Session not found or expired: {session_id}",
            code="SESSION_NOT_FOUND",
        )


class SessionExpiredException(DomainException):
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Session has expired: {session_id}",
            code="SESSION_EXPIRED",
        )


class ExternalAuthException(DomainException):
    def __init__(self, message: str = "External authentication failed"):
        super().__init__(message=message, code="EXTERNAL_AUTH_ERROR")


class BrowserLoginException(DomainException):
    def __init__(self, message: str, steps: list):
        super().__init__(message=message, code="BROWSER_LOGIN_ERROR")
        self.steps = steps


class ExternalRequestException(DomainException):
    def __init__(self, message: str):
        super().__init__(message=message, code="EXTERNAL_REQUEST_ERROR")
