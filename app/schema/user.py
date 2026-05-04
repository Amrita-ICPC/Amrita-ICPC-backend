from datetime import date, datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.utils.enums import UserRole


class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None


class UserBasicInfo(BaseModel):
    """Minimal user information for sharing and metadata views."""

    id: UUID
    user_id: str
    name: str
    email: EmailStr

    class Config:
        from_attributes = True


class UserProfile(UserBase):
    id: str
    roles: List[str] = []
    groups: List[str] = []

    class Config:
        from_attributes = True


class UserSyncSkipped(BaseModel):
    user_id: str
    name: Optional[str] = None
    reason: str


class UserSyncResponse(BaseModel):
    status: str
    message: str
    users_synced: int
    skipped_count: int
    skipped_users: List[UserSyncSkipped] = []
    synced_by: dict


class AudienceBasicInfo(BaseModel):
    id: UUID
    name: str

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    id: UUID
    user_id: str
    name: str
    email: EmailStr
    phone_no: Optional[str] = None
    role: UserRole
    gender: Optional[str] = None
    dob: Optional[date] = None
    created_at: datetime
    last_updated: datetime
    audience_links: List[AudienceBasicInfo] = []

    @field_validator("audience_links", mode="before")
    @classmethod
    def flatten_audience_links(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [getattr(item, "audience", item) for item in v]
        return v

    class Config:
        from_attributes = True
