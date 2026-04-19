from __future__ import annotations

from uuid import UUID

from app.models.audience import Audience
from app.repositories.dto.audience import (
    AudienceRoleCounts,
    CreateAudienceData,
    UpdateAudienceData,
)
from app.schema.audience import AudienceCreate, AudienceResponse, AudienceUpdate


def build_create_audience_dto(payload: AudienceCreate) -> CreateAudienceData:
    """Build a repository DTO from an audience create request.

    Args:
        payload: Incoming create request payload.

    Returns:
        CreateAudienceData DTO.
    """
    return CreateAudienceData(
        name=payload.name,
        audience_type=payload.audience_type,
        description=payload.description,
    )


def build_update_audience_dto(payload: AudienceUpdate) -> UpdateAudienceData:
    """Build a repository DTO from an audience update request.

    Args:
        payload: Incoming update request payload.

    Returns:
        UpdateAudienceData DTO.
    """
    return UpdateAudienceData(
        name=payload.name,
        audience_type=payload.audience_type,
        description=payload.description,
    )


def build_audience_entity(dto: CreateAudienceData) -> Audience:
    """Create an Audience ORM entity from a creation DTO.

    Args:
        dto: CreateAudienceData DTO.

    Returns:
        Audience ORM entity.
    """
    return Audience(
        name=dto.name,
        audience_type=dto.audience_type,
        description=dto.description,
    )


def apply_audience_update(audience: Audience, dto: UpdateAudienceData) -> Audience:
    """Apply an update DTO onto an existing audience entity.

    Args:
        audience: Audience ORM entity to mutate.
        dto: UpdateAudienceData DTO.

    Returns:
        The mutated Audience entity.
    """
    if dto.name is not None:
        audience.name = dto.name
    if dto.audience_type is not None:
        audience.audience_type = dto.audience_type
    if dto.description is not None:
        audience.description = dto.description
    return audience


def to_audience_response(
    audience: Audience, *, counts: AudienceRoleCounts | None = None
) -> AudienceResponse:
    """Convert an Audience ORM entity to response schema.

    Args:
        audience: Audience ORM entity.

    Returns:
        AudienceResponse schema.
    """
    role_counts = counts or AudienceRoleCounts(
        manager_count=0,
        instructor_count=0,
        student_count=0,
        total_users=0,
    )

    return AudienceResponse(
        id=audience.id,
        name=audience.name,
        audience_type=audience.audience_type,
        description=audience.description,
        manager_count=role_counts.manager_count,
        instructor_count=role_counts.instructor_count,
        student_count=role_counts.student_count,
        total_users=role_counts.total_users,
    )


def to_audience_response_list(audiences: list[Audience]) -> list[AudienceResponse]:
    """Convert a list of Audience ORM entities to response schema list.

    Args:
        audiences: List of Audience ORM entities.

    Returns:
        List of AudienceResponse schemas.
    """
    return [to_audience_response(audience) for audience in audiences]


def normalize_user_ids(user_ids: list[UUID]) -> list[UUID]:
    """Normalize a user-id list by de-duplicating while preserving order.

    Args:
        user_ids: Input user IDs.

    Returns:
        De-duplicated user IDs in stable order.
    """
    return list(dict.fromkeys(user_ids))
