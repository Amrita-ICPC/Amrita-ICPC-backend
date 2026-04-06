import asyncio
import io
from uuid import UUID

from minio import Minio

from app.core.clients.minio import get_minio_client
from app.core.config import config


class CodeStorageService:
    """Reusable MinIO-backed code storage service."""

    @staticmethod
    def build_code_object_key(
        resource_type: str,
        resource_id: UUID | str,
        *,
        filename: str | None = None,
        suffix: str = ".txt",
    ) -> str:
        """Build a stable MinIO object key for code-related content.

        The generated key is safe to reuse across the project for question source
        code, submission code, templates, or any other code payload.
        """
        safe_resource_type = resource_type.strip("/")
        safe_resource_id = str(resource_id).strip("/")

        if filename:
            safe_filename = filename.strip("/")
            return f"code/{safe_resource_type}/{safe_resource_id}/{safe_filename}"

        return f"code/{safe_resource_type}/{safe_resource_id}{suffix}"

    @staticmethod
    async def upload_code(
        object_key: str,
        code: str | bytes,
        *,
        content_type: str = "text/plain; charset=utf-8",
    ) -> str:
        """Upload a code payload to MinIO and return the object key."""
        client = get_minio_client()
        payload = code.encode("utf-8") if isinstance(code, str) else code
        stream = io.BytesIO(payload)

        def _upload(minio_client: Minio) -> None:
            minio_client.put_object(
                bucket_name=config.MINIO_BUCKET_NAME,
                object_name=object_key,
                data=stream,
                length=len(payload),
                content_type=content_type,
            )

        await asyncio.to_thread(_upload, client)
        return object_key

    @staticmethod
    async def get_code(object_key: str) -> str:
        """Download a code payload from MinIO and decode it as UTF-8 text."""
        raw_bytes = await CodeStorageService.get_code_bytes(object_key)
        return raw_bytes.decode("utf-8")

    @staticmethod
    async def get_code_bytes(object_key: str) -> bytes:
        """Download a code payload from MinIO as raw bytes."""
        client = get_minio_client()

        def _download(minio_client: Minio) -> bytes:
            response = minio_client.get_object(
                bucket_name=config.MINIO_BUCKET_NAME,
                object_name=object_key,
            )
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await asyncio.to_thread(_download, client)

    @staticmethod
    async def delete_code(object_key: str) -> None:
        """Delete a code payload from MinIO."""
        client = get_minio_client()

        def _delete(minio_client: Minio) -> None:
            minio_client.remove_object(
                bucket_name=config.MINIO_BUCKET_NAME,
                object_name=object_key,
            )

        await asyncio.to_thread(_delete, client)


# Backward-compatible function aliases.
build_code_object_key = CodeStorageService.build_code_object_key
upload_code = CodeStorageService.upload_code
get_code = CodeStorageService.get_code
get_code_bytes = CodeStorageService.get_code_bytes
delete_code = CodeStorageService.delete_code
