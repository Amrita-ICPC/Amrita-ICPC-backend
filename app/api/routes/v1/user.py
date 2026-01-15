from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.schema.user import UserProfile

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
