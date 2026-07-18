"""Schemas for image upload/download operations."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ImageUploadResponse(BaseModel):
    """Response schema for an uploaded image.

    Attributes:
        folder: Storage folder/prefix used for the object key.
        resource_id: Random resource identifier used to scope the upload.
        object_key: Object key stored in MinIO.
        url: Stable backend URL that redirects through a fresh presigned MinIO URL.
        bucket_name: MinIO bucket name.
        content_type: MIME type stored for the object.
        size_bytes: Size of the uploaded file in bytes.
        original_filename: Filename provided by the client.
    """

    folder: str = Field(..., description="Storage folder/prefix")
    resource_id: UUID = Field(..., description="Generated resource identifier")
    object_key: str = Field(..., description="MinIO object key")
    url: str = Field(..., description="Stable backend URL for accessing the image")
    bucket_name: str = Field(..., description="MinIO bucket name")
    content_type: str | None = Field(None, description="Stored MIME content type")
    size_bytes: int = Field(..., ge=0, description="Uploaded size in bytes")
    original_filename: str | None = Field(None, description="Original client filename")
