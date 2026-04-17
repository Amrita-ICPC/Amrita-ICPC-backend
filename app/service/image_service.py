"""Service for image upload operations.

This module provides a minimal, reusable service that stores uploaded images in
MinIO and returns metadata suitable for API responses.

The service is intentionally storage-only (no database access) so it can be
used independently by multiple domains (contests, profiles, etc.).
"""

from __future__ import annotations

import io
import os
import uuid

from fastapi import UploadFile
from minio import Minio

from app.core.clients.minio import get_minio_client
from app.exceptions.image import (
    ImageStorageError,
    InvalidImageDataError,
    InvalidImagePathError,
)
from app.schema.image import ImageUploadResponse
from app.utils.image import image_object_key_to_url


class ImageService:
    """Service layer for uploading images to object storage."""

    async def upload_image(
        self, file: UploadFile, *, folder: str = "contest", bucket_name: str = "icpc"
    ) -> ImageUploadResponse:
        """Upload an image file and return metadata.

        The object key is constructed as `<folder>/<random_uuid>/<random_name>`.
        By default, `folder` is `contest`.

        Args:
            file: Uploaded file from a multipart request.
            folder: Folder/prefix to group uploads.

        Returns:
            ImageUploadResponse: Uploaded image metadata including URL and object key.

        Raises:
            InvalidImageDataError: If the uploaded file is empty or not an image.
            InvalidImagePathError: If folder/filename results in an unsafe object key.
            ImageStorageError: If object storage upload fails.
        """

        content_type = getattr(file, "content_type", None)
        if content_type and not content_type.startswith("image/"):
            raise InvalidImageDataError("only image/* content types are allowed")

        data = await file.read()
        if not data:
            raise InvalidImageDataError("uploaded file is empty")

        resource_id = uuid.uuid4()
        filename = _sanitize_filename(file.filename or "image")
        safe_folder = _sanitize_folder(folder)

        random_name = f"{uuid.uuid4().hex}{_safe_extension(filename)}"

        object_key = f"{safe_folder}/{resource_id}/{random_name}"
        client = get_minio_client()
        _ensure_bucket_exists(client, bucket_name)

        try:
            client.put_object(
                bucket_name=bucket_name,
                object_name=object_key,
                data=io.BytesIO(data),
                length=len(data),
                content_type=content_type or "application/octet-stream",
            )
        except Exception as exc:
            raise ImageStorageError(
                "Failed to upload image to object storage",
                detail={
                    "bucket": bucket_name,
                    "object_key": object_key,
                    "error": str(exc),
                },
            ) from exc

        url = image_object_key_to_url(object_key, bucket_name=bucket_name)
        if url is None:
            raise ImageStorageError(
                "Failed to derive image URL",
                detail={"bucket": bucket_name, "object_key": object_key},
            )

        return ImageUploadResponse(
            folder=safe_folder,
            resource_id=resource_id,
            object_key=object_key,
            url=url,
            bucket_name=bucket_name,
            content_type=content_type,
            size_bytes=len(data),
            original_filename=file.filename,
        )


def _safe_extension(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if not ext:
        return ""
    if len(ext) > 10:
        return ""
    if not ext.startswith("."):
        return ""
    if not all(ch.isalnum() for ch in ext[1:]):
        return ""
    return ext


def _sanitize_folder(folder: str) -> str:
    """Sanitize a storage folder prefix.

    Args:
        folder: Folder prefix.

    Returns:
        Sanitized prefix without leading/trailing slashes.

    Raises:
        InvalidImagePathError: If the prefix is empty or unsafe.
    """

    normalized = folder.replace("\\", "/").strip().strip("/")
    if not normalized:
        raise InvalidImagePathError("folder cannot be empty")
    if any(part in {".", "..", ""} for part in normalized.split("/")):
        raise InvalidImagePathError("folder contains invalid path segments")
    return normalized


def _sanitize_filename(filename: str) -> str:
    """Sanitize an uploaded filename.

    Args:
        filename: Filename provided by the client.

    Returns:
        A safe filename.

    Raises:
        InvalidImagePathError: If the filename is empty or unsafe.
    """

    base = os.path.basename(filename).strip().strip("/")
    if not base or base in {".", ".."}:
        raise InvalidImagePathError("filename is invalid")
    if "/" in base or "\\" in base:
        raise InvalidImagePathError("filename must not contain path separators")
    return base


def _ensure_bucket_exists(client: Minio, bucket_name: str) -> None:
    """Ensure the target bucket exists in MinIO.

    Args:
        client: Initialized MinIO client.
        bucket_name: Bucket to create if missing.

    Raises:
        ImageStorageError: If bucket check/create fails.
    """

    try:
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
    except Exception as exc:
        raise ImageStorageError(
            "Failed to ensure image bucket exists",
            detail={"bucket": bucket_name, "error": str(exc)},
        ) from exc
