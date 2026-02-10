from typing import List, Optional

from pydantic import BaseModel, EmailStr


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

