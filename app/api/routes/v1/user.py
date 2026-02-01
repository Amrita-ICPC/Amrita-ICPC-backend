from typing import Any, Dict

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import get_current_user, require_admin
from app.core.clients.database import get_db
from app.core.logger import logger
from app.schema.user import UserProfile
from app.service.user_service import UserService

router = APIRouter()


@router.get("/")
def get_users():
    return [{"id": 1, "name": "User 1"}]


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


@router.post("/")
def create_user():
    return {"message": "User created"}


@router.post("/sync-keycloak-users", status_code=status.HTTP_200_OK)
def sync_keycloak_users(
    admin_user: Dict[str, Any] = Depends(require_admin),
    db=Depends(get_db),
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
        f"Keycloak user sync initiated by admin: {admin_name} ({admin_email}) [ID: {admin_id}]"
    )

    # Sync Keycloak users (exception handled in service layer)
    users_synced = UserService.sync_keycloak_users(db)

    logger.info(
        f"Keycloak user sync completed successfully: {users_synced} users synced by {admin_name} ({admin_email})"
    )

    return {
        "status": "success",
        "message": "Keycloak users synced successfully",
        "users_synced": users_synced,
        "synced_by": {
            "name": admin_name,
            "email": admin_email,
            "id": admin_id
        }
    }