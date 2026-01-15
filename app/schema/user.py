from pydantic import BaseModel, EmailStr
from typing import Optional, List

class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class UserProfile(UserBase):
    id: str
    roles: List[str] = []
    groups: List[str] = []

    class Config:
        from_attributes = True
