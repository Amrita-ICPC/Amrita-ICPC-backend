from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_user_id, require_admin
from app.core.clients.database import get_db
from app.core.logger import logger
from app.core.response import create_api_response
from app.repositories.dto.user import UserListFilters
from app.schema.base import APIResponse
from app.schema.user import UserProfile, UserResponse, UserSyncResponse
from app.service.user_service import UserService
from app.utils.enums import UserRole
from app.utils.pagination import get_pagination

router = APIRouter()


@router.get("/me", response_model=UserProfile)
def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get current logged-in user details from JWT."""
    return {
        "id": current_user.get("sub"),
        "name": current_user.get("name"),
        "email": current_user.get("email"),
        "roles": current_user.get("roles", []),
        "groups": current_user.get("groups", []),
    }


@router.post(
    "/sync-keycloak-users",
    response_model=UserSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def sync_keycloak_users(
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Synchronize Keycloak users with the local database.

    Only administrators can trigger this operation. This endpoint fetches all users
    from Keycloak, retrieves their group assignments, and creates new user records
    in the database if they don't already exist.

    Args:
        admin_user: Current authenticated admin user
        db: Database session

    Returns:
        Response with sync status and number of users synced

    Raises:
        PermissionDeniedError: If user is not an admin
        KeycloakSyncError: If sync operation fails
    """
    admin_id = admin_user.get("sub")
    admin_email = admin_user.get("email", "unknown")
    admin_name = admin_user.get("name", "unknown")

    logger.info(
        "Keycloak user sync initiated by admin: %s (%s) [ID: %s]",
        admin_name,
        admin_email,
        admin_id,
    )

    # Sync Keycloak users (exception handled in service layer)
    sync_result = await UserService.sync_keycloak_users(db)

    users_synced = sync_result["synced_count"]
    skipped_count = sync_result["skipped_count"]

    logger.info(
        "Keycloak user sync completed: %s synced, %s skipped. Initiated by %s (%s)",
        users_synced,
        skipped_count,
        admin_name,
        admin_email,
    )

    return {
        "status": "success",
        "message": "Keycloak users sync completed",
        "users_synced": users_synced,
        "skipped_count": skipped_count,
        "skipped_users": sync_result["skipped_users"],
        "synced_by": {"name": admin_name, "email": admin_email, "id": admin_id},
    }


@router.get(
    "/",
    response_model=APIResponse[list[UserResponse]],
    summary="List users",
    dependencies=[Depends(require_admin)],
)
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    role: UserRole | None = Query(None, description="Filter by user role"),
    q: str | None = Query(None, description="Search by name, email, or phone number"),
):
    """List users with filtering and pagination.

    This endpoint is accessible only to administrators.

    Args:
        request: FastAPI request context.
        db: Database session.
        page: Page number for pagination.
        page_size: Number of items per page.
        role: Optional filter for user role.
        q: Optional search query for name, email, or phone number.

    Returns:
        Paginated list of users.
    """
    skip = (page - 1) * page_size

    filters = UserListFilters(skip=skip, limit=page_size, role=role, query=q)
    total, users = await UserService.list_users(db, filters, actor_id=user_id)
    pagination = get_pagination(total=total, page=page, page_size=page_size)
    return create_api_response(
        request,
        data=users,
        message="Users fetched successfully",
        pagination=pagination,
    )
