from uuid import UUID

from app.models.contest import Contest
from app.repositories.dto.contest import CreateContestData, UpdateContestData
from app.schema.contest import (
    ContestCreate,
    ContestResponse,
    ContestSummaryResponse,
    ContestUpdate,
)


def build_create_contest_dto(
    contest: ContestCreate, created_by: UUID
) -> CreateContestData:
    """Map contest creation schema to repository create DTO."""
    return CreateContestData(
        name=contest.name,
        description=contest.description,
        image=contest.image,
        is_public=contest.is_public,
        start_time=contest.start_time,
        end_time=contest.end_time,
        registration_start=contest.registration_start,
        registration_end=contest.registration_end,
        max_teams=contest.max_teams,
        min_team_size=contest.min_team_size,
        max_team_size=contest.max_team_size,
        rules=contest.rules,
        scoring_type=contest.scoring_type,
        team_approval_mode=contest.team_approval_mode,
        created_by=created_by,
    )


def build_update_contest_dto(contest_data: ContestUpdate) -> UpdateContestData:
    """Map contest update schema to repository update DTO."""
    return UpdateContestData(
        name=contest_data.name,
        description=contest_data.description,
        image=contest_data.image,
        is_public=contest_data.is_public,
        start_time=contest_data.start_time,
        end_time=contest_data.end_time,
        registration_start=contest_data.registration_start,
        registration_end=contest_data.registration_end,
        max_teams=contest_data.max_teams,
        min_team_size=contest_data.min_team_size,
        max_team_size=contest_data.max_team_size,
        rules=contest_data.rules,
        scoring_type=contest_data.scoring_type,
        team_approval_mode=contest_data.team_approval_mode,
    )


def to_contest_response(contest) -> ContestResponse:
    """Map contest ORM object to detail response schema."""
    return ContestResponse.model_validate(contest)


def to_contest_summary_response(contest) -> ContestSummaryResponse:
    """Map contest ORM object to summary response schema."""
    return ContestSummaryResponse.model_validate(contest)


def build_contest_entity(contest_data: CreateContestData) -> Contest:
    """Map contest create DTO to ORM entity."""
    return Contest(
        name=contest_data.name,
        description=contest_data.description,
        image=contest_data.image,
        is_public=contest_data.is_public,
        start_time=contest_data.start_time,
        end_time=contest_data.end_time,
        registration_start=contest_data.registration_start,
        registration_end=contest_data.registration_end,
        max_teams=contest_data.max_teams,
        min_team_size=contest_data.min_team_size,
        max_team_size=contest_data.max_team_size,
        rules=contest_data.rules,
        scoring_type=contest_data.scoring_type,
        team_approval_mode=contest_data.team_approval_mode,
        created_by=contest_data.created_by,
    )


def apply_contest_updates(contest: Contest, update_data: UpdateContestData) -> None:
    """Apply contest update DTO values onto ORM entity."""
    update_dict = update_data.__dict__
    for field, value in update_dict.items():
        if value is not None:
            setattr(contest, field, value)
