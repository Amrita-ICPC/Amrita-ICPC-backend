from typing import Any, ClassVar, Optional


class AppBaseException(Exception):
    """Base category for application exceptions.

    Subclasses may set a class-level ``error_code`` to control the "code"
    field the API returns for that exception type (see
    app.api.errors.app_exception_handler, the single handler that serves
    every AppBaseException subclass unless one needs a genuinely different
    response shape). Falls back to the class name if unset.
    """

    error_code: ClassVar[Optional[str]] = None

    def __init__(
        self, message: str, status_code: int = 500, detail: Optional[Any] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail or message
