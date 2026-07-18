"""Service for image upload and download operations.

This module stores uploaded images in MinIO and returns stable API metadata.

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
from app.core.config import config
from app.exceptions.image import (
    ImageStorageError,
    InvalidImageDataError,
    InvalidImagePathError,
)
from app.schema.image import ImageUploadResponse
from app.utils.image import create_presigned_image_url, image_object_key_to_url

# Magic-byte signatures for the small allowlist of raster formats accepted
# here. Deliberately excludes SVG: SVG is XML and can embed <script>/
# event-handler payloads that execute if the stored object is ever viewed
# inline in a browser (stored XSS), and it has no fixed magic-byte signature
# to anchor a check on in the first place.
_MEDIA_TYPE_EXTENSIONS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _detect_image_media_type(data: bytes) -> str | None:
    """Sniff the actual image format from file bytes.

    The client-supplied ``Content-Type`` header and filename extension are
    both trivially spoofable (a request can label an SVG payload as
    "image/png" with a ".png" filename) -- this is the only check here that
    looks at what was actually uploaded, and its result is what determines
    the stored extension and Content-Type, not anything the client sent.

    Returns:
        The canonical media type string if recognized, else None.
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class ImageService:
    """Service layer for image object storage and signed download URLs."""

    async def upload_image(
        self, file: UploadFile, *, folder: str = "contest", bucket_name: str | None = None
    ) -> ImageUploadResponse:
        """Upload an image file and return metadata.

        The object key is constructed as `<folder>/<random_uuid>/<random_name>`.
        By default, `folder` is `contest`.

        Args:
            file: Uploaded file from a multipart request.
            folder: Folder/prefix to group uploads.
            bucket_name: Optional bucket override. Defaults to MINIO_BUCKET_NAME.

        Returns:
            ImageUploadResponse: Uploaded image metadata including a stable access URL.

        Raises:
            InvalidImageDataError: If the uploaded file is empty, exceeds the
                size limit, or is not a recognized image format.
            InvalidImagePathError: If folder/filename results in an unsafe object key.
            ImageStorageError: If object storage upload fails.
        """

        data = await file.read()
        if not data:
            raise InvalidImageDataError("uploaded file is empty")
        if len(data) > config.IMAGE_MAX_UPLOAD_SIZE_BYTES:
            raise InvalidImageDataError(
                f"uploaded file exceeds the {config.IMAGE_MAX_UPLOAD_SIZE_BYTES} "
                "byte limit"
            )

        # Authoritative type check: sniffed from bytes, not the client-supplied
        # Content-Type header or filename extension (see _detect_image_media_type).
        media_type = _detect_image_media_type(data)
        if media_type is None:
            raise InvalidImageDataError(
                "file content is not a recognized image format "
                "(png/jpeg/gif/webp); other formats including svg are not accepted"
            )

        # Still validated for path-safety even though it no longer determines
        # the stored extension -- it's echoed back as original_filename below.
        _sanitize_filename(file.filename or "image")

        resource_id = uuid.uuid4()
        safe_folder = _sanitize_folder(folder)
        target_bucket = bucket_name or config.MINIO_BUCKET_NAME

        random_name = f"{uuid.uuid4().hex}{_MEDIA_TYPE_EXTENSIONS[media_type]}"

        object_key = f"{safe_folder}/{resource_id}/{random_name}"
        client = get_minio_client()
        _ensure_bucket_exists(client, target_bucket)

        try:
            client.put_object(
                bucket_name=target_bucket,
                object_name=object_key,
                data=io.BytesIO(data),
                length=len(data),
                content_type=media_type,
            )
        except Exception as exc:
            raise ImageStorageError(
                "Failed to upload image to object storage",
                detail={
                    "bucket": target_bucket,
                    "object_key": object_key,
                    "error": str(exc),
                },
            ) from exc

        url = image_object_key_to_url(object_key, bucket_name=target_bucket)
        if url is None:
            raise ImageStorageError(
                "Failed to derive stable image URL",
                detail={"bucket": target_bucket, "object_key": object_key},
            )

        return ImageUploadResponse(
            folder=safe_folder,
            resource_id=resource_id,
            object_key=object_key,
            url=url,
            bucket_name=target_bucket,
            content_type=media_type,
            size_bytes=len(data),
            original_filename=file.filename,
        )

    def create_presigned_download_url(self, *, bucket_name: str, object_key: str) -> str:
        """Create a short-lived MinIO URL for the stable backend image route."""

        if bucket_name != config.MINIO_BUCKET_NAME:
            raise InvalidImagePathError("unsupported image bucket")

        _validate_object_key(object_key)

        try:
            return create_presigned_image_url(bucket_name, object_key)
        except Exception as exc:
            raise ImageStorageError(
                "Failed to create image download URL",
                detail={
                    "bucket": bucket_name,
                    "object_key": object_key,
                    "error": str(exc),
                },
            ) from exc


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


def _validate_object_key(object_key: str) -> None:
    """Validate a stored MinIO object key before signing it."""

    normalized = object_key.replace("\\", "/").strip().strip("/")
    if normalized != object_key:
        raise InvalidImagePathError("object key must be normalized")
    if any(part in {".", "..", ""} for part in normalized.split("/")):
        raise InvalidImagePathError("object key contains invalid path segments")


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
