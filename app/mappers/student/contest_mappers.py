"""Mapper functions for student contest responses.

Transforms ORM Contest objects and repository data into student-facing API response schemas.
Centralizes all contest response building logic in one place for easy maintenance and reusability.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.schema.student.contests import (
    StudentContestAvailableResponse,
    StudentContestDetailsResponse,
    StudentContestListResponse,
    StudentContestProblemResponse,
    StudentContestProblemsListResponse,
    StudentRegisteredContestListResponse,
    StudentRegisteredContestResponse,
)

if TYPE_CHECKING:
    from app.models.contest import Contest, ContestQuestion, ContestTeam
    from app.models.team import Team
    from app.repositories.dto import PaginatedResult


def to_student_available_contest_response(
    contest: "Contest", problem_count: int = 0
) -> StudentContestAvailableResponse:
    """
    Convert Contest ORM object to StudentContestAvailableResponse.
    
    Maps a contest to the response shown in the available contests list.
    Includes contest metadata and team configuration but hides instructor details.
    
    Args:
        contest: Contest ORM object from database
        problem_count: Number of problems in the contest (pre-calculated for performance)
    
    Returns:
        StudentContestAvailableResponse ready for API response
    """
    return StudentContestAvailableResponse(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        image=contest.image,
        start_time=contest.start_time,
        end_time=contest.end_time,
        registration_start=contest.registration_start,
        registration_end=contest.registration_end,
        status=contest.status,
        is_public=contest.is_public,
        problem_count=problem_count,
        team_approval_mode=contest.team_approval_mode,
        min_team_size=contest.min_team_size,
        max_team_size=contest.max_team_size,
    )


def to_student_available_contests_list_response(
    paginated_result: "PaginatedResult",
    skip: int,
    limit: int,
) -> StudentContestListResponse:
    """
    Convert paginated Contest results to StudentContestListResponse.
    
    Transforms a PaginatedResult of Contest objects into a paginated list response.
    Calculates problem counts and includes pagination metadata.
    
    Args:
        paginated_result: PaginatedResult containing Contest objects
        skip: Number of items skipped (for pagination info)
        limit: Limit used in query (for pagination info)
    
    Returns:
        StudentContestListResponse with pagination and contest list
    """
    contests = [
        to_student_available_contest_response(contest, problem_count=len(contest.questions))
        for contest in paginated_result.items
    ]
    
    total = paginated_result.total
    has_more = (skip + limit) < total
    
    return StudentContestListResponse(
        contests=contests,
        total=total,
        page=(skip // limit) + 1 if limit > 0 else 1,
        page_size=limit,
        has_more=has_more,
    )


def to_student_registered_contest_response(
    contest: "Contest",
    contest_team: "ContestTeam" | None = None,
    team: "Team" | None = None,
    problem_count: int = 0,
) -> StudentRegisteredContestResponse:
    """
    Convert Contest ORM object to StudentRegisteredContestResponse.
    
    Maps a contest where student is registered to response including
    registration timestamp and team information.
    
    Args:
        contest: Contest ORM object from database
        contest_team: ContestTeam object linking student's team to contest
        team: Team object that student is registered with
        problem_count: Number of problems in the contest
    
    Returns:
        StudentRegisteredContestResponse with registration details
    """
    return StudentRegisteredContestResponse(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        image=contest.image,
        start_time=contest.start_time,
        end_time=contest.end_time,
        registration_start=contest.registration_start,
        registration_end=contest.registration_end,
        status=contest.status,
        is_public=contest.is_public,
        problem_count=problem_count,
        team_approval_mode=contest.team_approval_mode,
        min_team_size=contest.min_team_size,
        max_team_size=contest.max_team_size,
        registered_at=contest_team.enrolled_at if contest_team else datetime.utcnow(),
        registered_as_team=True,
        team_id=team.id if team else None,
        team_name=team.name if team else None,
    )


def to_student_registered_contests_list_response(
    paginated_result: "PaginatedResult",
    skip: int,
    limit: int,
) -> StudentRegisteredContestListResponse:
    """
    Convert paginated registered Contest results to StudentRegisteredContestListResponse.
    
    Args:
        paginated_result: PaginatedResult containing tuples of (Contest, ContestTeam)
        skip: Number of items skipped (for pagination info)
        limit: Limit used in query (for pagination info)
    
    Returns:
        StudentRegisteredContestListResponse with pagination and contest list
    """
    contests = [
        to_student_registered_contest_response(
            contest,
            contest_team=contest_team,
            team=contest_team.team if contest_team else None,
            problem_count=len(contest.questions),
        )
        for contest, contest_team in paginated_result.items
    ]
    
    total = paginated_result.total
    has_more = (skip + limit) < total
    
    return StudentRegisteredContestListResponse(
        contests=contests,
        total=total,
        page=(skip // limit) + 1 if limit > 0 else 1,
        page_size=limit,
        has_more=has_more,
    )


def to_student_contest_problem_response(
    question: "ContestQuestion",
) -> StudentContestProblemResponse:
    """
    Convert ContestQuestion ORM object to StudentContestProblemResponse.
    
    Maps a problem within a contest to the student's view, showing only
    student-relevant information (title, difficulty, score, time limit).
    
    Args:
        question: ContestQuestion ORM object representing a problem in contest
    
    Returns:
        StudentContestProblemResponse with problem details
    """
    return StudentContestProblemResponse(
        id=question.question_id,
        order=question.order,
        title=question.question.title,
        difficulty=question.question.difficulty.value,
        score=question.score,
        duration=question.duration,
    )


def to_student_contest_details_response(
    contest: "Contest",
    problems: list["ContestQuestion"],
    is_student_registered: bool,
    user_id: UUID,
) -> StudentContestDetailsResponse:
    """
    Convert Contest ORM and problems to StudentContestDetailsResponse.
    
    Builds complete contest details including all problems and student's
    registration status. Used for the detailed contest view endpoint.
    
    Args:
        contest: Contest ORM object
        problems: List of ContestQuestion objects for this contest
        is_student_registered: Whether current student is registered
        user_id: Current student's UUID (for logging)
    
    Returns:
        StudentContestDetailsResponse with full contest and problem details
    """
    problem_responses = [to_student_contest_problem_response(p) for p in problems]
    
    return StudentContestDetailsResponse(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        image=contest.image,
        start_time=contest.start_time,
        end_time=contest.end_time,
        registration_start=contest.registration_start,
        registration_end=contest.registration_end,
        status=contest.status,
        is_public=contest.is_public,
        rules=contest.rules,
        team_approval_mode=contest.team_approval_mode,
        min_team_size=contest.min_team_size,
        max_team_size=contest.max_team_size,
        show_leaderboard=contest.show_leaderboard,
        problems=problem_responses,
        student_registered=is_student_registered,
        student_team_id=None,  # Will be populated by service if needed
    )


def to_student_contest_problems_list_response(
    contest: "Contest",
    problems: list["ContestQuestion"],
) -> StudentContestProblemsListResponse:
    """
    Convert Contest and problems to StudentContestProblemsListResponse.
    
    Builds a list of problems for a specific contest.
    
    Args:
        contest: Contest ORM object
        problems: List of ContestQuestion objects for this contest
    
    Returns:
        StudentContestProblemsListResponse with problems and metadata
    """
    problem_responses = [to_student_contest_problem_response(p) for p in problems]
    
    return StudentContestProblemsListResponse(
        contest_id=contest.id,
        contest_name=contest.name,
        problems=problem_responses,
        total_problems=len(problem_responses),
    )
