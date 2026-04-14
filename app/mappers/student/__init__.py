"""Student mappers for transforming ORM objects to API response schemas.

Provides centralized data transformation functions for student-facing endpoints.
Contains contest and team mappers for converting ORM objects → DTOs → Response schemas.
"""

from app.mappers.student.contest_mappers import (
    to_student_available_contest_response,
    to_student_available_contests_list_response,
    to_student_contest_details_response,
    to_student_contest_problem_response,
    to_student_contest_problems_list_response,
    to_student_registered_contest_response,
    to_student_registered_contests_list_response,
)
from app.mappers.student.team_mappers import (
    to_student_available_team_response,
    to_student_available_teams_list_response,
    to_student_leave_team_response,
    to_student_team_create_and_join_response,
    to_student_team_join_response,
    to_student_team_member_response,
    to_student_team_response,
    to_student_teams_list_response,
)

__all__ = [
    # Contest mappers
    "to_student_available_contest_response",
    "to_student_available_contests_list_response",
    "to_student_registered_contest_response",
    "to_student_registered_contests_list_response",
    "to_student_contest_details_response",
    "to_student_contest_problems_list_response",
    "to_student_contest_problem_response",
    # Team mappers
    "to_student_team_member_response",
    "to_student_team_response",
    "to_student_teams_list_response",
    "to_student_available_team_response",
    "to_student_available_teams_list_response",
    "to_student_team_join_response",
    "to_student_team_create_and_join_response",
    "to_student_leave_team_response",
]
