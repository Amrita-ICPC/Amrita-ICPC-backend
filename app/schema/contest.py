from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ContestBase(BaseModel):
    """Base schema for contest with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Contest name")
    description: Optional[str] = Field(
        None, max_length=5000, description="Contest description"
    )
    image: Optional[str] = Field(None, description="Contest image URL")
    is_public: bool = Field(default=False, description="Whether contest is public")


class ContestCreate(ContestBase):
    """Schema for creating a contest."""

    pass


class ContestUpdate(BaseModel):
    """Schema for updating a contest."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Contest name"
    )
    description: Optional[str] = Field(
        None, max_length=5000, description="Contest description"
    )
    image: Optional[str] = Field(None, description="Contest image URL")
    is_public: Optional[bool] = Field(None, description="Whether contest is public")


class ContestResponse(ContestBase):
    """Schema for contest response."""

    id: UUID = Field(..., description="Contest ID")

    class Config:
        from_attributes = True


class ContestListResponse(BaseModel):
    """Schema for contest list response."""

    total: int = Field(..., description="Total number of contests")
    contests: List[ContestResponse] = Field(..., description="List of contests")


class MessageResponse(BaseModel):
    """Schema for message response."""

    message: str = Field(..., description="Response message")

