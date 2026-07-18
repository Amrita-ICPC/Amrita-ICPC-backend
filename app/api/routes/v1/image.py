"""Image upload routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import RedirectResponse

from app.auth.dependencies import can_create, get_current_user_id
from app.core.response import create_api_response
from app.schema.base import APIResponse
from app.schema.image import ImageUploadResponse
from app.service.image_service import ImageService

router = APIRouter()


def get_image_service() -> ImageService:
    """Provide an ImageService instance.

    Returns:
        ImageService: Service that uploads images to object storage.
    """

    return ImageService()


@router.post(
    "/upload",
    response_model=APIResponse[ImageUploadResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image",
    dependencies=[can_create("contests")],
)
async def upload_image(
    request: Request,
    file: UploadFile = File(..., description="Image file to upload"),
    _user_id=Depends(get_current_user_id),
    service: ImageService = Depends(get_image_service),
) -> APIResponse[ImageUploadResponse]:
    """Upload an image and return storage metadata.

    This endpoint stores the image in MinIO under a key shaped like
    `contest/<random_uuid>/<random_name>` and returns a stable backend URL.

    Args:
        request: Framework request context.
        file: Multipart-uploaded image file.
        _user_id: Authenticated user ID (used only for auth enforcement).
        service: Injected ImageService.

    Returns:
        APIResponse[ImageUploadResponse]: Upload metadata with `object_key` and a stable `url`.

    Raises:
        UnauthorizedError: If the caller is not authenticated.
        PermissionDeniedError: If the caller lacks permission.
        InvalidImageDataError: If the payload is empty or not an image.
        InvalidImagePathError: If the derived object key is unsafe.
        ImageStorageError: If upload to object storage fails.
    """

    uploaded = await service.upload_image(file, folder="contest")
    return create_api_response(
        request,
        data=uploaded,
        message="Image uploaded successfully",
        status_code=status.HTTP_201_CREATED,
    )

@router.get(
    "/images/{bucket_name}/{object_key:path}",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    summary="Download image",
)
async def download_image(
    bucket_name: str,
    object_key: str,
    service: ImageService = Depends(get_image_service),
) -> RedirectResponse:
    """Redirect a stable backend image URL to a fresh presigned MinIO URL."""

    presigned_url = service.create_presigned_download_url(
        bucket_name=bucket_name,
        object_key=object_key,
    )
    return RedirectResponse(
        url=presigned_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
