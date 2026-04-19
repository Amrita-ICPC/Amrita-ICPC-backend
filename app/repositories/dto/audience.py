from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from app.utils.enums import AudienceType

if TYPE_CHECKING:
    from app.models.audience import Audience


@dataclass(frozen=True, slots=True)
class AudienceRoleCounts:
    """Aggregated audience membership counts by role."""

    manager_count: int
    instructor_count: int
    student_count: int
    total_users: int


@dataclass(frozen=True, slots=True)
class AudienceWithCounts:
    """Audience ORM entity bundled with its membership counts."""

    audience: "Audience"
    counts: AudienceRoleCounts


@dataclass(frozen=True, slots=True)
class CreateAudienceData:
    """DTO for creating a new audience."""

    name: str
    audience_type: AudienceType
    description: str | None


@dataclass(frozen=True, slots=True)
class UpdateAudienceData:
    """DTO for updating an existing audience."""

    name: str | None = None
    audience_type: AudienceType | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class AudienceUserBulkData:
    """DTO for bulk audience-user membership changes."""

    audience_id: UUID
    user_ids: list[UUID]
