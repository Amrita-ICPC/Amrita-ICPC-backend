from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_user_id, require_admin
from app.core.clients.database import get_db
from app.core.logger import logger
from app.core.response import create_api_response
from app.repositories.audience import AudienceRepository
from app.repositories.dto.audience import AudienceUserBulkDataEmail
from app.repositories.user import UserRepository
from app.schema.audience import (
    AudienceAddUsersByEmailResponse,
    AudienceCreate,
    AudienceResponse,
    AudienceUpdate,
    AudienceUsersBulkRequest,
    AudienceUsersResponse,
)
from app.schema.base import APIResponse
from app.service.audience_service import AudienceService
from app.utils.enums import UserRole
from app.utils.pagination import get_pagination

router = APIRouter()


def get_audience_service(db: AsyncSession = Depends(get_db)) -> AudienceService:
    """Create an AudienceService instance.

    Args:
        db: Database session provided by FastAPI.

    Returns:
        Fully wired AudienceService.
    """
    return AudienceService(
        repository=AudienceRepository(db),
        user_repository=UserRepository(db),
    )


@router.post(
    "/",
    response_model=APIResponse[AudienceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create an audience",
    dependencies=[Depends(require_admin)],
)
async def create_audience(
    request: Request,
    payload: AudienceCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AudienceService = Depends(get_audience_service),
):
    """Create a new audience.

    Args:
        request: FastAPI request context.
        payload: Audience creation payload.
        current_user: Authenticated user payload from Keycloak.
        service: Injected audience service.

    Returns:
        Standard APIResponse containing the created audience.

    Raises:
        AudienceAlreadyExistsError: If an audience with the same name exists.
        PermissionDeniedError: If the caller is not an admin.
    """
    created = await service.create_audience(payload)
    logger.info(
        "Audience '%s' created by user %s",
        created.name,
        current_user.get("preferred_username"),
    )
    return create_api_response(
        request,
        data=created,
        message="Audience created successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/",
    response_model=APIResponse[list[AudienceResponse]],
    summary="List audiences",
    dependencies=[Depends(require_admin)],
)
async def list_audiences(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    q: str | None = Query(None, description="Optional search by audience name"),
    actor_id: UUID = Depends(get_current_user_id),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AudienceService = Depends(get_audience_service),
):
    """List all audiences.

    Args:
        request: FastAPI request context.
        page: Page number (1-indexed).
        page_size: Page size.
        q: Optional substring filter applied to audience names.
        current_user: Authenticated user payload from Keycloak.
        service: Injected audience service.

    Returns:
        Standard APIResponse containing audiences and pagination metadata.

    Raises:
        PermissionDeniedError: If the caller is not an admin.
    """
    skip = (page - 1) * page_size
    total, audiences = await service.list_audiences(
        skip=skip,
        limit=page_size,
        query=q,
        actor_id=actor_id,
    )
    pagination = get_pagination(total=total, page=page, page_size=page_size)
    return create_api_response(
        request,
        data=audiences,
        message="Audiences fetched successfully",
        pagination=pagination,
    )


@router.get(
    "/{audience_id}",
    response_model=APIResponse[AudienceResponse],
    summary="Get an audience by ID",
    dependencies=[Depends(require_admin)],
)
async def get_audience(
    request: Request,
    audience_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AudienceService = Depends(get_audience_service),
):
    """Fetch a single audience.

    Args:
        request: FastAPI request context.
        audience_id: Audience identifier.
        current_user: Authenticated user payload from Keycloak.
        service: Injected audience service.

    Returns:
        Standard APIResponse containing the audience.

    Raises:
        AudienceNotFoundError: If the audience does not exist.
        PermissionDeniedError: If the caller is not an admin.
    """
    audience = await service.get_audience(audience_id)
    return create_api_response(
        request, data=audience, message="Audience fetched successfully"
    )


@router.patch(
    "/{audience_id}",
    response_model=APIResponse[AudienceResponse],
    summary="Update an audience",
    dependencies=[Depends(require_admin)],
)
async def update_audience(
    request: Request,
    audience_id: UUID,
    payload: AudienceUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AudienceService = Depends(get_audience_service),
):
    """Update an audience.

    Args:
        request: FastAPI request context.
        audience_id: Audience identifier.
        payload: Update payload.
        current_user: Authenticated user payload from Keycloak.
        service: Injected audience service.

    Returns:
        Standard APIResponse containing the updated audience.

    Raises:
        AudienceNotFoundError: If the audience does not exist.
        AudienceAlreadyExistsError: If the updated name conflicts.
        PermissionDeniedError: If the caller is not an admin.
    """
    updated = await service.update_audience(audience_id, payload)
    logger.info(
        "Audience %s updated by user %s",
        audience_id,
        current_user.get("preferred_username"),
    )
    return create_api_response(
        request, data=updated, message="Audience updated successfully"
    )


@router.delete(
    "/{audience_id}",
    response_model=APIResponse,
    summary="Delete an audience",
    dependencies=[Depends(require_admin)],
)
async def delete_audience(
    request: Request,
    audience_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AudienceService = Depends(get_audience_service),
):
    """Delete an audience.

    Args:
        request: FastAPI request context.
        audience_id: Audience identifier.
        current_user: Authenticated user payload from Keycloak.
        service: Injected audience service.

    Returns:
        Standard APIResponse with a success message.

    Raises:
        AudienceNotFoundError: If the audience does not exist.
        PermissionDeniedError: If the caller is not an admin.
    """
    await service.delete_audience(audience_id)
    logger.info(
        "Audience %s deleted by user %s",
        audience_id,
        current_user.get("preferred_username"),
    )
    return create_api_response(request, message="Audience deleted successfully")


@router.get(
    "/{audience_id}/users",
    response_model=APIResponse[AudienceUsersResponse],
    summary="List users in an audience",
    dependencies=[Depends(require_admin)],
)
async def list_audience_users(
    request: Request,
    audience_id: UUID,
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    q: str | None = Query(
        None, description="Optional search by name, email, or phone number"
    ),
    role: UserRole | None = Query(None, description="Optional role filter"),
    actor_id: UUID = Depends(get_current_user_id),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AudienceService = Depends(get_audience_service),
):
    """List users belonging to an audience.

    Args:
        request: FastAPI request context.
        audience_id: Audience identifier.
        page: Page number (1-indexed).
        page_size: Page size.
        q: Optional substring filter applied to user name, email, or phone number.
        role: Optional role filter.
        current_user: Authenticated user payload from Keycloak.
        service: Injected audience service.

    Returns:
        Standard APIResponse containing users and pagination metadata.

    Raises:
        AudienceNotFoundError: If the audience does not exist.
        PermissionDeniedError: If the caller is not an admin.
    """
    skip = (page - 1) * page_size
    total, response = await service.list_audience_users(
        audience_id,
        skip=skip,
        limit=page_size,
        actor_id=actor_id,
        role=role,
        query=q,
    )
    pagination = get_pagination(total=total, page=page, page_size=page_size)
    return create_api_response(
        request,
        data=response,
        message="Audience users fetched successfully",
        pagination=pagination,
    )


@router.post(
    "/{audience_id}/users",
    response_model=APIResponse,
    summary="Add users to an audience in bulk",
    dependencies=[Depends(require_admin)],
)
async def add_users_to_audience(
    request: Request,
    audience_id: UUID,
    payload: AudienceUsersBulkRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AudienceService = Depends(get_audience_service),
):
    """Add users to an audience.

    Args:
        request: FastAPI request context.
        audience_id: Audience identifier.
        payload: Bulk user IDs to add.
        current_user: Authenticated user payload from Keycloak.
        service: Injected audience service.

    Returns:
        Standard APIResponse with a success message.

    Raises:
        AudienceNotFoundError: If the audience does not exist.
        UserNotFoundError: If any user ID does not exist.
        PermissionDeniedError: If the caller is not an admin.
    """
    await service.add_users_to_audience(audience_id, payload.user_ids)
    logger.info(
        "Added %s users to audience %s by user %s",
        len(payload.user_ids),
        audience_id,
        current_user.get("preferred_username"),
    )
    return create_api_response(request, message="Users added to audience successfully")


@router.delete(
    "/{audience_id}/users",
    response_model=APIResponse[int],
    summary="Remove users from an audience in bulk",
    dependencies=[Depends(require_admin)],
)
async def remove_users_from_audience(
    request: Request,
    audience_id: UUID,
    payload: AudienceUsersBulkRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AudienceService = Depends(get_audience_service),
):
    """Remove users from an audience.

    Args:
        request: FastAPI request context.
        audience_id: Audience identifier.
        payload: Bulk user IDs to remove.
        current_user: Authenticated user payload from Keycloak.
        service: Injected audience service.

    Returns:
        Standard APIResponse containing the number of removed links.

    Raises:
        AudienceNotFoundError: If the audience does not exist.
        UserNotFoundError: If any user ID does not exist.
        PermissionDeniedError: If the caller is not an admin.
    """
    removed_count = await service.remove_users_from_audience(
        audience_id,
        payload.user_ids,
    )
    logger.info(
        "Removed %s users from audience %s by user %s",
        len(payload.user_ids),
        audience_id,
        current_user.get("preferred_username"),
    )
    return create_api_response(
        request,
        data=removed_count,
        message="Users removed from audience successfully",
    )


@router.post(
    "/{audience_id}/users/email",
    response_model=APIResponse[AudienceAddUsersByEmailResponse],
    summary="Add users to an audience in bulk by email",
    dependencies=[Depends(require_admin)],
)
async def add_users_to_audience_by_email(
    request: Request,
    audience_id: UUID,
    payload: AudienceUserBulkDataEmail,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: AudienceService = Depends(get_audience_service),
) -> APIResponse[AudienceAddUsersByEmailResponse]:
    """Add users to an audience by their email addresses.

    Args:
        request: FastAPI request context.
        audience_id: Audience identifier.
        payload: Bulk user emails to add.
        current_user: Authenticated user payload from Keycloak.
        service: Injected audience service.

    Returns:
        Standard APIResponse with a success message.

    Raises:
        AudienceNotFoundError: If the audience does not exist.
        PermissionDeniedError: If the caller is not an admin.
    """
    result = await service.add_bulk_users_to_audience_by_email(audience_id, payload)
    logger.info(
        "Added %s users to audience %s by email by user %s (%s already present, %s not found)",
        result.added,
        audience_id,
        current_user.get("preferred_username"),
        result.already_present,
        result.not_found,
    )
    return create_api_response(
        request, message="Users added to audience successfully", data=result
    )
