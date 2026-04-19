"""Pydantic schemas for the audience domain.

Audiences are named groupings of users used to target contest visibility or other
scoped features.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import AudienceType


class AudienceCreate(BaseModel):
    """Request payload for creating an audience."""

    name: str = Field(..., min_length=1, max_length=255, description="Audience name")
    audience_type: AudienceType = Field(
        ...,
        description="Audience type (e.g., class, campus)",
    )
    description: str | None = Field(
        None, max_length=5000, description="Optional audience description"
    )


class AudienceUpdate(BaseModel):
    """Request payload for updating an audience."""

    name: str | None = Field(
        None, min_length=1, max_length=255, description="Audience name"
    )
    audience_type: AudienceType | None = Field(
        None,
        description="Audience type (e.g., class, campus)",
    )
    description: str | None = Field(
        None, max_length=5000, description="Optional audience description"
    )


class AudienceResponse(BaseModel):
    """Response payload representing an audience."""

    id: UUID = Field(..., description="Audience identifier")
    name: str = Field(..., description="Audience name")
    audience_type: AudienceType = Field(..., description="Audience type")
    description: str | None = Field(None, description="Audience description")

    manager_count: int = Field(0, ge=0, description="Number of managers")
    instructor_count: int = Field(0, ge=0, description="Number of instructors")
    student_count: int = Field(0, ge=0, description="Number of students")
    total_users: int = Field(0, ge=0, description="Total number of users")

    model_config = ConfigDict(from_attributes=True)


class AudienceUsersBulkRequest(BaseModel):
    """Request payload for bulk audience membership changes."""

    user_ids: list[UUID] = Field(
        ..., min_length=1, description="User IDs to add/remove in bulk"
    )
