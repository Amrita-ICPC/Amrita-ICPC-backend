from fastapi import status
from app.exceptions.base import AppBaseException

class UnauthorizedError(AppBaseException):
    """Raised when authentication fails."""
    def __init__(self, message: str = "Could not validate credentials"):
        super().__init__(message=message, status_code=status.HTTP_401_UNAUTHORIZED)

class TokenExpiredError(UnauthorizedError):
    """Raised when the JWT token has expired."""
    def __init__(self, message: str = "Token has expired"):
        super().__init__(message=message)

class PermissionDeniedError(AppBaseException):
    """Raised when user doesn't have required permissions."""
    def __init__(self, message: str = "Not enough permissions"):
        super().__init__(message=message, status_code=status.HTTP_403_FORBIDDEN)

class RoleMissingError(PermissionDeniedError):
    """Raised when user doesn't have a specific role."""
    def __init__(self, role: str):
        super().__init__(message=f"Missing required role: {role}")
