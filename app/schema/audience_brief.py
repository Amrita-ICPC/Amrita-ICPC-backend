"""Pydantic schemas for brief audience list responses.

These schemas are used for endpoints that need to return a lightweight audience
projection (for example, showing the audiences visible to the current user)
without additional counts or metadata.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.utils.enums import AudienceType


class AudienceBriefResponse(BaseModel):
    """Response payload representing a minimal audience object.

    Attributes:
        id: Audience identifier.
        name: Audience name.
        type: Audience type.
    """

    id: UUID = Field(..., description="Audience identifier")
    name: str = Field(..., description="Audience name")
    type: AudienceType = Field(..., description="Audience type")
