from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schema.question import QuestionResponse
from app.utils.enums import BankPermission



class BankBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Bank name")
    description: Optional[str] = Field(None, max_length=5000, description="Bank description")


class BankCreate(BankBase):
    pass


class BankUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255, description="Bank name")
    description: Optional[str] = Field(None, max_length=5000, description="Bank description")


class BankResponse(BankBase):
    id: UUID = Field(..., description="Bank ID")
    created_by: UUID = Field(..., description="Creator user ID")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Last update time")

    class Config:
        from_attributes = True


class BankShareBase(BaseModel):
    user_id: UUID
    permission: BankPermission

    class Config:
        from_attributes = True


class BankDetailResponse(BankResponse):
    questions: List[QuestionResponse] = []
    shares: List[BankShareBase] = []


class BankListResponse(BaseModel):
    total: int = Field(..., description="Total number of banks")
    banks: List[BankResponse] = Field(..., description="List of banks")


class BankShareItem(BaseModel):
    user_id: UUID = Field(..., description="User ID to share with")
    permission: BankPermission = Field(
        default=BankPermission.read, description="Permission level"
    )


class BankShareRequest(BaseModel):
    shares: List[BankShareItem] = Field(..., description="List of users to share with")


class BankUnshareRequest(BaseModel):
    user_ids: List[UUID] = Field(..., description="List of user IDs to remove access for")