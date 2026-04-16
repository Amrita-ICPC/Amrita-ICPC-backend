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


# Response Mappers: ORM → API Schemas


def to_student_available_contest_response(
    contest: "Contest", problem_count: int = 0
) -> StudentContestAvailableResponse:
    """
    Map Contest ORM object to student available contest response.
    
    Used in GET /students/contests/available endpoint.
    Transforms a public contest into summary view for discovery.
    
    Includes:
        - Contest metadata (name, description, image)
        - Time windows (start, end, registration periods)
        - Status and visibility (public, status flag)
        - Team configuration (size constraints, approval mode)
        - Problem count for summary display
    
    Excludes:
        - Instructor details
        - Scoring configuration
        - Student registration status
        - Leaderboard settings
    
    Args:
        contest: Contest ORM object from database
        problem_count: Number of problems in contest (for efficient list queries)
    
    Returns:
        StudentContestAvailableResponse ready for API serialization
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
    Map paginated Contest results to paginated list response.
    
    Used in GET /students/contests/available with pagination.
    
    Transformation Process:
        1. Extract Contest objects from PaginatedResult
        2. Calculate problem counts from contest.questions
        3. Map each contest to summary response
        4. Calculate pagination metadata (page, has_more)
    
    Args:
        paginated_result: PaginatedResult containing Contest ORM objects
        skip: Number of items skipped (0-based offset)
        limit: Number of items per page
    
    Returns:
        StudentContestListResponse with paginated contest summaries
    """
    contests = [
        to_student_available_contest_response(contest, problem_count=len(contest.questions))
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


def to_student_registered_contest_response(
    contest: "Contest",
    contest_team: "ContestTeam" | None = None,
    team: "Team" | None = None,
    problem_count: int = 0,
) -> StudentRegisteredContestResponse:
    """
    Map Contest ORM to student registered contest response.
    
    Used in GET /students/contests/registered endpoint.
    Shows contests student is already registered in with team details.
    
    Includes all available contest info plus:
        - Registration timestamp (when enrolled)
        - Team information (id, name)
        - Registration context (registered_as_team flag)
    
    Args:
        contest: Contest ORM object from database
        contest_team: ContestTeam linking student's team to contest (optional)
        team: Team ORM object student is registered with (optional)
        problem_count: Number of problems in contest (pre-calculated for performance)
    
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
    Map paginated registered Contest results to paginated list response.
    
    Used in GET /students/contests/registered with pagination.
    
    Transformation Process:
        1. Extract (Contest, ContestTeam) tuples from PaginatedResult
        2. Calculate problem counts and extract team info
        3. Map each registered contest with team details
        4. Calculate pagination metadata
    
    Args:
        paginated_result: PaginatedResult containing (Contest, ContestTeam) tuples
        skip: Number of items skipped (0-based offset)
        limit: Number of items per page
    
    Returns:
        StudentRegisteredContestListResponse with paginated registered contests
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
    current_page = (skip // limit) + 1 if limit > 0 else 1
    
    return StudentRegisteredContestListResponse(
        contests=contests,
        total=total,
        page=current_page,
        page_size=limit,
        has_more=has_more,
    )


def to_student_contest_problem_response(
    question: "ContestQuestion",
) -> StudentContestProblemResponse:
    """
    Map ContestQuestion ORM to student problem response.
    
    Transforms a problem within a contest into the student view.
    Shows only student-relevant information:
        - Problem identity and order
        - Difficulty level
        - Score/points
        - Time limit
    
    Hides:
        - Judge details
        - Test case information
        - Solution references
        - Instructor notes
    
    Args:
        question: ContestQuestion ORM object linking question to contest
    
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
    Map Contest ORM and problems to detailed contest response.
    
    Used in GET /students/contests/{id}/details endpoint.
    Builds comprehensive contest view for registered students.
    
    Transformation Process:
        1. Map each problem to student problem response
        2. Include all contest metadata
        3. Include student's registration status
        4. Prepare for detailed student view
    
    Args:
        contest: Contest ORM object from database
        problems: List of ContestQuestion objects for this contest
        is_student_registered: Whether current student is registered
        user_id: Current student's UUID (for audit/logging)
    
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
        student_team_id=None,  # Populated by service layer if needed
    )


def to_student_contest_problems_list_response(
    contest: "Contest",
    problems: list["ContestQuestion"],
) -> StudentContestProblemsListResponse:
    """
    Map Contest and problems to problems list response.
    
    Used in GET /students/contests/{id}/problems endpoint.
    Returns all problems for a specific contest with metadata.
    
    Args:
        contest: Contest ORM object from database
        problems: List of ContestQuestion objects in contest
    
    Returns:
        StudentContestProblemsListResponse with problems list and count
    """
    problem_responses = [to_student_contest_problem_response(p) for p in problems]
    
    return StudentContestProblemsListResponse(
        contest_id=contest.id,
        contest_name=contest.name,
        problems=problem_responses,
        total_problems=len(problem_responses),
    )
