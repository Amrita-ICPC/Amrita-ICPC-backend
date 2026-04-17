"""Image URL utilities.

This module contains small helpers for working with image object keys stored in
object storage (MinIO).
"""

from __future__ import annotations

from urllib.parse import quote

from app.core.config import config


def image_object_key_to_url(
    object_key: str | None, *, bucket_name: str | None = None
) -> str | None:
    """Derive a public image URL from a MinIO object key.

    Uses `MINIO_HOST` and `MINIO_PORT` from config.

    If the object key is empty (None/""), returns None.

    Args:
        object_key: MinIO object key/path (e.g. "contest/<uuid>/<name>.png").
        bucket_name: Optional bucket name (defaults to config.MINIO_BUCKET_NAME).

    Returns:
        A public URL, or the original empty value.
    """

    if not object_key:
        return None

    # Defensive: some unit tests/mocks may provide non-string values.
    if not isinstance(object_key, str):
        return None

    # If callers accidentally pass a full URL, keep it unchanged.
    if "://" in object_key:
        return object_key

    bucket = bucket_name or config.MINIO_BUCKET_NAME
    scheme = "https" if config.MINIO_SECURE else "http"
    endpoint = f"{config.MINIO_HOST}:{config.MINIO_PORT}"
    quoted_key = quote(object_key, safe="/")
    return f"{scheme}://{endpoint}/{bucket}/{quoted_key}"
