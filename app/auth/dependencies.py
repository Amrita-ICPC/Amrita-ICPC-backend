from typing import Any, Dict, List, cast
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clients.database import get_db
from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError, UnauthorizedError
from app.schema.user import UserResponse
from app.service.user_service import UserService


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Retrieve the user object from the request.
    This object is populated by fastapi-keycloak-middleware.
    """
    if not hasattr(request, "user") or request.user is None:
        raise UnauthorizedError("No authenticated user found")

    # fastapi-keycloak-middleware populates request.user with an object.
    # By default, it's a FastApiUser object where claims are attributes.
    # To maintain compatibility with our existing dict-based logic:
    user = request.user

    # If user is already a dict (custom mapper used), good.
    if isinstance(user, dict):
        return cast(Dict[str, Any], user)

    if hasattr(user, "__dict__"):
        return cast(Dict[str, Any], user.__dict__)

    raise UnauthorizedError("Invalid user object")


def get_user_roles(user: Dict[str, Any]) -> List[str]:
    """Extract roles from user object."""
    # Roles are directly mapped
    return cast(List[str], user.get("roles", []))


def get_user_groups(user: Dict[str, Any]) -> List[str]:
    """Extract groups from user object."""
    # Groups are directly mapped
    return cast(List[str], user.get("groups", []))


class AccessControl:
    """
    Unified Access Control Checker.
    Supports checking Roles, Groups, and Permissions (resource:action).
    """

    def __init__(
        self,
        allowed_roles: List[str] | None = None,
        allowed_groups: List[str] | None = None,
        permission: str | None = None,  # Format: "resource:action" e.g., "teams:create"
    ):
        self.allowed_roles = allowed_roles or []
        self.allowed_groups = allowed_groups or []
        self.permission = permission

    def __call__(self, user: Dict[str, Any] = Depends(get_current_user)):
        user_roles = get_user_roles(user)
        user_groups = get_user_groups(user)

        # 1. Check Groups (High-level check)
        # If user has one of the allowed groups, access is granted irrespective of specific roles within that scope
        # (Assuming groups imply broad access, or check strict intersection)
        if self.allowed_groups:
            has_group = any(group in user_groups for group in self.allowed_groups)
            # Alternatively, check normalized group names like "/custom_group" -> "custom_group"
            if not has_group:
                # remove leading slash often sending by keycloak i.e. /admin -> admin
                normalized_groups = [g.lstrip("/") for g in user_groups]
                has_group = any(
                    group in normalized_groups for group in self.allowed_groups
                )

            if has_group:
                return user

        # 2. Check Roles
        if self.allowed_roles:
            has_role = any(role in user_roles for role in self.allowed_roles)
            if has_role:
                return user

        # 3. Check Permissions
        # Logic: User needs ONE of:
        # - "admin" role (Superuser)
        # - Exact "resource:action" role
        # - "resource:*" role
        # - "resource:CRUD" concept if implemented
        if self.permission:
            resource, action = self.permission.split(":", 1)
            required_perms = [
                self.permission,  # "teams:create"
                f"{resource}:*",  # "teams:*"
                f"{resource}:CRUD",  # "teams:CRUD" (Custom convention)
                "admin",  # Superuser bypass
            ]

            has_perm = any(perm in user_roles for perm in required_perms)
            if has_perm:
                return user

        # If any requirement was set but not met
        if self.allowed_groups or self.allowed_roles or self.permission:
            err_msg = []
            if self.allowed_groups:
                err_msg.append(f"groups={self.allowed_groups}")
            if self.allowed_roles:
                err_msg.append(f"roles={self.allowed_roles}")
            if self.permission:
                err_msg.append(f"perm={self.permission}")

            logger.warning(
                f"Access denied for user {user.get('preferred_username')}. Missing: {', '.join(err_msg)}"
            )
            raise PermissionDeniedError("Insufficient permissions")

        return user


# --- Predefined Wrappers / Aliases ---

# Group Wrappers
admin_procedure = Depends(AccessControl(allowed_groups=["admin"]))
instructor_procedure = Depends(AccessControl(allowed_groups=["instructor"]))
student_procedure = Depends(AccessControl(allowed_groups=["student"]))


# Role Primitive
def has_role(roles: List[str]):
    return AccessControl(allowed_roles=roles)


def require_admin(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Dependency to ensure only admin users can access the protected endpoint.

    Args:
        user: Current authenticated user

    Returns:
        Current user if they have admin role

    Raises:
        PermissionDeniedError: If user is not an admin
    """
    user_roles = get_user_roles(user)
    user_groups = get_user_groups(user)

    # Normalize group names (remove leading slash)
    normalized_groups = [g.lstrip("/") for g in user_groups]

    # Check if user is admin via roles or groups
    is_admin = "admin" in user_roles or "admin" in normalized_groups

    if not is_admin:
        logger.warning(
            f"Unauthorized admin action attempted by user {user.get('preferred_username')}"
        )
        raise PermissionDeniedError("Admin privileges required for this operation")

    return user


# Permission Primitives
def check_permission(resource: str, action: str):
    return AccessControl(permission=f"{resource}:{action}")


def can_create(resource: str):
    return Depends(check_permission(resource, "create"))


def can_read(resource: str):
    return Depends(check_permission(resource, "read"))


def can_update(resource: str):
    return Depends(check_permission(resource, "update"))


async def get_current_user_id(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """
    Retrieve the current authenticated user's database ID.

    This dependency avoids repeated database lookups by leveraging the UserService.
    """
    kc_id = current_user.get("sub")
    if kc_id is None:
        raise UnauthorizedError("No authenticated user found")
    # UserService.get_user_by_keycloak_id is cached, so efficient
    user: UserResponse = await UserService.get_user_by_keycloak_id(db, kc_id)
    return user.id


def can_delete(resource: str):
    return Depends(check_permission(resource, "delete"))
