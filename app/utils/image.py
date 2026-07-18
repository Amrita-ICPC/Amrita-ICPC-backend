"""Image URL utilities.

This module contains helpers for turning MinIO object keys into stable
application URLs backed by short-lived MinIO presigned redirects.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote, unquote, urlsplit

from app.core.clients.minio import get_minio_client
from app.core.config import config


def image_object_key_to_url(
    object_key: str | None, *, bucket_name: str | None = None
) -> str | None:
    """Create a stable backend image URL for a stored MinIO object key.

    The returned URL is durable enough to persist in contest records or
    Markdown. The backend route issues a fresh presigned MinIO URL on each
    browser request, so the MinIO bucket does not need anonymous read access.

    Existing direct MinIO URLs for the configured MinIO endpoint are normalized
    back to the backend image route. Non-MinIO external URLs are returned
    unchanged for backwards compatibility.
    """

    if not object_key:
        return None

    if not isinstance(object_key, str):
        return None

    bucket = bucket_name or config.MINIO_BUCKET_NAME
    key = object_key

    if "://" in object_key:
        parsed_direct = _direct_minio_url_to_bucket_and_key(object_key)
        if parsed_direct is None:
            return object_key
        bucket, key = parsed_direct

    return _image_route_url(bucket, key)


def create_presigned_image_url(bucket_name: str, object_key: str) -> str:
    """Create a short-lived MinIO download URL for a private image object."""

    expires = timedelta(seconds=config.MINIO_PRESIGNED_URL_EXPIRY_SECONDS)
    return get_minio_client().presigned_get_object(
        bucket_name=bucket_name,
        object_name=object_key,
        expires=expires,
    )


def _image_route_url(bucket_name: str, object_key: str) -> str:
    api_base_url = _public_api_base_url()
    quoted_bucket = quote(bucket_name, safe="")
    quoted_key = quote(object_key, safe="/")
    return f"{api_base_url}/images/{quoted_bucket}/{quoted_key}"


def _public_api_base_url() -> str:
    if config.API_PUBLIC_BASE_URL:
        return config.API_PUBLIC_BASE_URL.rstrip("/")

    prefix = config.API_PREFIX.rstrip("/")
    return f"http://{config.API_HOST}:{config.API_PORT}{prefix}/v1"


def _direct_minio_url_to_bucket_and_key(url: str) -> tuple[str, str] | None:
    parsed = urlsplit(url)
    if parsed.netloc != f"{config.MINIO_HOST}:{config.MINIO_PORT}":
        return None

    path = parsed.path.lstrip("/")
    if "/" not in path:
        return None

    bucket, key = path.split("/", 1)
    if not bucket or not key:
        return None

    return unquote(bucket), unquote(key)
