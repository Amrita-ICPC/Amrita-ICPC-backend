from typing import Any, Dict, Optional

class AppBaseException(Exception):
    """Base category for application exceptions."""
    def __init__(
        self, 
        message: str, 
        status_code: int = 500, 
        detail: Optional[Any] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail or message
