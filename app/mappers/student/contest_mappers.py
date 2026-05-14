"""
Mapper functions for student contest operations and responses.

Centralizes all ORM-to-response and request-to-DTO transformations for student contest operations.
Maintains consistency between API schemas and internal data models.

Mapper Organization:
    - Response Mappers: ORM → API Response Schemas
      - to_student_available_contest_response() - Single contest to summary response
      - to_student_available_contests_list_response() - Paginated contest list
      - to_student_registered_contest_response() - Single registered contest
      - to_student_registered_contests_list_response() - Paginated registered list
      - to_student_contest_details_response() - Full contest with problems
      - to_student_contest_problem_response() - Single problem in contest
      - to_student_contest_problems_list_response() - All problems in contest

Key Principles:
    - Pure functions: No side effects, deterministic outputs
    - Type safety: Explicit parameter and return types
    - Documentation: Comprehensive docstrings with use cases
    - Reusability: Share common transformation logic
"""

from datetime import datetime
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from app.schema.student.contests import (
    StudentContestAvailableResponse,
    StudentContestListResponse,
)

if TYPE_CHECKING:
    from app.models.contest import Contest, ContestQuestion, ContestTeam
    from app.models.team import Team
    from app.repositories.dto import PaginatedResult
from app.utils.enums import ContestRunStatus
from app.utils.image import image_object_key_to_url
from app.schema.contest import ContestAudienceResponse


# Response Mappers: ORM → API Schemas


def to_student_available_contest_response(
    contest: "Contest", 
    *, 
    teams_count: int = 0,
    run_status: ContestRunStatus
) -> StudentContestAvailableResponse:
    """
    Map Contest ORM object and extra data to student available contest response.
    """
    return StudentContestAvailableResponse(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        image=image_object_key_to_url(contest.image),
        start_time=contest.start_time,
        end_time=contest.end_time,
        registration_start=contest.registration_start,
        registration_end=contest.registration_end,
        status=contest.status,
        run_status=run_status,
        created_at=contest.created_at,
        is_public=contest.is_public,
        team_approval_mode=contest.team_approval_mode,
        contest_mode=contest.contest_mode,
        audiences=[
            ContestAudienceResponse.model_validate(link.audience)
            for link in contest.audience_links
        ] if contest.audience_links else [],
        max_teams=contest.max_teams,
        min_team_size=contest.min_team_size,
        max_team_size=contest.max_team_size,
        teams_count=teams_count,
    )


def to_student_available_contests_list_response(
    paginated_result: "PaginatedResult",
    skip: int,
    limit: int,
    teams_count_dict: dict[UUID, int],
    run_status_calculator: Callable[[datetime, datetime], ContestRunStatus],
) -> StudentContestListResponse:
    """
    Map paginated Contest results and team counts to paginated list response.
    """
    contests = [
        to_student_available_contest_response(
            contest, 
            teams_count=teams_count_dict.get(contest.id, 0),
            run_status=run_status_calculator(contest.start_time, contest.end_time)
        )
        for contest in paginated_result.items
    ]
    
    total = paginated_result.total
    has_more = (skip + limit) < total
    current_page = (skip // limit) + 1 if limit > 0 else 1
    
    return StudentContestListResponse(
        contests=contests,
        total=total,
        page=current_page,
        page_size=limit,
        has_more=has_more,
    )