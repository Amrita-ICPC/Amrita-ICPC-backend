from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.utils.enums import UserRole


class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None


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

    class Config:
        from_attributes = True
