"""Image storage exceptions.

This module contains domain-specific exceptions raised by image upload/download
operations.

The exceptions are designed to map cleanly to HTTP status codes via the central
FastAPI exception handlers.
"""

from __future__ import annotations

from fastapi import status

from app.exceptions.base import AppBaseException


class InvalidImagePathError(AppBaseException):
    """Raised when an object key or filename is invalid.

    Args:
        message: Human-readable validation error message.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message=f"Invalid image path: {message}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class InvalidImageDataError(AppBaseException):
    """Raised when uploaded image data is invalid.

    Args:
        message: Human-readable validation error message.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message=f"Invalid image data: {message}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class ImageNotFoundError(AppBaseException):
    """Raised when an image object is not found in object storage.

    Args:
        object_key: Object key that was not found.
    """

    def __init__(self, object_key: str) -> None:
        super().__init__(
            message="Image not found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"object_key": object_key},
        )


class ImageStorageError(AppBaseException):
    """Raised when an upstream object storage operation fails.

    Args:
        message: Human-readable failure message.
        detail: Optional structured details.
    """

    def __init__(self, message: str, *, detail: object | None = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail or message,
        )
