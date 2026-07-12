from typing import cast
from uuid import UUID

from app.models.contest import Contest
from app.repositories.dto.contest import UNSET, CreateContestData, UpdateContestData
from app.schema.contest import (
    ContestAudienceResponse,
    ContestCreate,
    ContestResponse,
    ContestSummaryResponse,
    ContestUpdate,
)
from app.utils.enums import ContestRunStatus
from app.utils.image import image_object_key_to_url


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
        team_approval_mode=contest.team_approval_mode,
        contest_mode=contest.contest_mode,
        audience_ids=contest.audience_ids,
        created_by=created_by,
        duration=contest.duration,
        show_leaderboard_during_contest=contest.show_leaderboard_during_contest,
        participation_type=contest.participation_type,
        evaluate_on_submit=contest.evaluate_on_submit,
        max_submission_per_question=contest.max_submission_per_question,
        show_leaderboard=contest.show_leaderboard,
        show_team_submissions=contest.show_team_submissions,
        shuffle_questions=contest.shuffle_questions,
    )


def build_update_contest_dto(contest_data: ContestUpdate) -> UpdateContestData:
    """Map contest update schema to repository update DTO."""
    fields_set = contest_data.model_fields_set

    # These columns are NOT NULL on the contest table. Clients sometimes send an
    # explicit ``null`` for them (e.g. the contest form clears the
    # participation-type widget when the mode is switched from team to
    # individual), which would otherwise be applied verbatim and blow up on
    # flush with a not-null violation. Treat an explicit null on a required
    # field as "leave unchanged" (UNSET) so a stray null can never blank it.
    non_nullable_fields = (
        "contest_mode",
        "participation_type",
        "team_approval_mode",
    )

    def _set(field_name: str):
        if field_name not in fields_set:
            return UNSET
        value = getattr(contest_data, field_name)
        if value is None and field_name in non_nullable_fields:
            return UNSET
        return value

    return UpdateContestData(
        name=contest_data.name if "name" in fields_set else UNSET,
        description=contest_data.description if "description" in fields_set else UNSET,
        image=contest_data.image if "image" in fields_set else UNSET,
        is_public=contest_data.is_public if "is_public" in fields_set else UNSET,
        start_time=contest_data.start_time if "start_time" in fields_set else UNSET,
        end_time=contest_data.end_time if "end_time" in fields_set else UNSET,
        contest_mode=_set("contest_mode"),
        registration_start=(
            contest_data.registration_start
            if "registration_start" in fields_set
            else UNSET
        ),
        registration_end=(
            contest_data.registration_end if "registration_end" in fields_set else UNSET
        ),
        max_teams=contest_data.max_teams if "max_teams" in fields_set else UNSET,
        min_team_size=(
            contest_data.min_team_size if "min_team_size" in fields_set else UNSET
        ),
        max_team_size=(
            contest_data.max_team_size if "max_team_size" in fields_set else UNSET
        ),
        rules=contest_data.rules if "rules" in fields_set else UNSET,
        team_approval_mode=_set("team_approval_mode"),
        duration=contest_data.duration if "duration" in fields_set else UNSET,
        show_leaderboard_during_contest=(
            contest_data.show_leaderboard_during_contest
            if "show_leaderboard_during_contest" in fields_set
            else UNSET
        ),
        participation_type=_set("participation_type"),
        evaluate_on_submit=(
            contest_data.evaluate_on_submit
            if "evaluate_on_submit" in fields_set
            else UNSET
        ),
        max_submission_per_question=(
            contest_data.max_submission_per_question
            if "max_submission_per_question" in fields_set
            else UNSET
        ),
        show_leaderboard=(
            contest_data.show_leaderboard if "show_leaderboard" in fields_set else UNSET
        ),
        show_team_submissions=(
            contest_data.show_team_submissions
            if "show_team_submissions" in fields_set
            else UNSET
        ),
        shuffle_questions=(
            contest_data.shuffle_questions
            if "shuffle_questions" in fields_set
            else UNSET
        ),
    )


def to_contest_response(
    contest: Contest,
    *,
    run_status: ContestRunStatus,
    team_count: int | None = None,
    question_count: int | None = None,
    submission_count: int | None = None,
    participant_count: int | None = None,
) -> ContestResponse:
    """Map contest ORM object to detail response schema.

    Args:
        contest: Contest ORM entity.
        run_status: Pre-computed temporal run-state (UPCOMING / LIVE / ENDED).
        team_count: Optional number of teams in the contest. When provided, the
            value is populated on the response.
        question_count: Optional number of questions in the contest.
        submission_count: Optional number of submissions for contest questions.
        participant_count: Optional number of distinct contest participants.

    Returns:
        Contest detail response schema.
    """

    response = ContestResponse(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        image=image_object_key_to_url(contest.image),
        is_public=contest.is_public,
        start_time=contest.start_time,
        end_time=contest.end_time,
        registration_start=contest.registration_start,
        registration_end=contest.registration_end,
        max_teams=contest.max_teams,
        min_team_size=contest.min_team_size,
        max_team_size=contest.max_team_size,
        team_count=team_count or 0,
        question_count=question_count or 0,
        submission_count=submission_count or 0,
        participant_count=participant_count or 0,
        rules=contest.rules,
        team_approval_mode=contest.team_approval_mode,
        contest_mode=contest.contest_mode,
        run_status=run_status,
        status=contest.status,
        created_by=cast(UUID, contest.created_by),
        creator=None,
        created_at=contest.created_at,
        updated_at=contest.updated_at,
        updated_by=contest.updated_by,
        published_at=contest.published_at,
        published_by=contest.published_by,
        duration=contest.duration,
        show_leaderboard_during_contest=contest.show_leaderboard_during_contest,
        participation_type=contest.participation_type,
        evaluate_on_submit=contest.evaluate_on_submit,
        max_submission_per_question=contest.max_submission_per_question,
        results_published_at=contest.results_published_at,
        show_leaderboard=contest.show_leaderboard,
        show_team_submissions=contest.show_team_submissions,
        shuffle_questions=contest.shuffle_questions,
    )

    return response


def to_contest_summary_response(
    contest: Contest, *, run_status: ContestRunStatus
) -> ContestSummaryResponse:
    """Map contest ORM object to summary response schema."""
    q_count = getattr(contest, "question_count", 0)
    t_count = getattr(contest, "team_count", 0)

    response = ContestSummaryResponse(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        image=image_object_key_to_url(contest.image),
        is_public=contest.is_public,
        start_time=contest.start_time,
        end_time=contest.end_time,
        team_approval_mode=contest.team_approval_mode,
        contest_mode=contest.contest_mode,
        run_status=run_status,
        status=contest.status,
        created_at=contest.created_at,
        duration=contest.duration,
        show_leaderboard_during_contest=contest.show_leaderboard_during_contest,
        participation_type=contest.participation_type,
        evaluate_on_submit=contest.evaluate_on_submit,
        max_submission_per_question=contest.max_submission_per_question,
        show_leaderboard=contest.show_leaderboard,
        show_team_submissions=contest.show_team_submissions,
        shuffle_questions=contest.shuffle_questions,
        audiences=[
            ContestAudienceResponse.model_validate(link.audience)
            for link in contest.audience_links
        ]
        if hasattr(contest, "audience_links")
        else [],
        question_count=q_count if isinstance(q_count, int) else 0,
        team_count=t_count if isinstance(t_count, int) else 0,
    )

    return response


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
        team_approval_mode=contest_data.team_approval_mode,
        contest_mode=contest_data.contest_mode,
        created_by=contest_data.created_by,
        duration=contest_data.duration,
        show_leaderboard_during_contest=contest_data.show_leaderboard_during_contest,
        participation_type=contest_data.participation_type,
        evaluate_on_submit=contest_data.evaluate_on_submit,
        max_submission_per_question=contest_data.max_submission_per_question,
        show_leaderboard=contest_data.show_leaderboard,
        show_team_submissions=contest_data.show_team_submissions,
        shuffle_questions=contest_data.shuffle_questions,
    )


def apply_contest_updates(contest: Contest, update_data: UpdateContestData) -> None:
    """Apply contest update DTO values onto ORM entity."""
    update_dict = update_data.__dict__
    for field, value in update_dict.items():
        if value is not UNSET:
            setattr(contest, field, value)
