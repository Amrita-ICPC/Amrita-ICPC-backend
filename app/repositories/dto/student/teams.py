"""
Data Transfer Objects for student team operations.

These DTOs bridge the repository layer and service layer for team-related queries
and operations from a student's perspective. They provide type-safe data transfer
without exposing ORM models directly.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.utils.enums import TeamStatus


@dataclass
class StudentTeamFilters:
    """Filters for querying teams from a student's perspective."""

    search_term: str | None = None
    created_only: bool = False   # If True, only teams created by the student
    leader_only: bool = False    # If True, only teams where user is leader
    min_size: int | None = None  # Minimum team member count filter
    max_size: int | None = None  # Maximum team member count filter
    is_public: bool | None = None  # Filter by public/private status


@dataclass
class StudentTeamMemberData:
    """
    Data transfer object for a team member in student view.

    Contains minimal member information visible within team context.
    """

    id: UUID
    name: str
    email: str
    is_leader: bool


@dataclass
class StudentTeamData:
    """
    Data transfer object for basic team information.

    Used for team retrieval and team listing endpoints.
    """

    id: UUID
    name: str
    description: str | None
    created_by: UUID
    leader_id: UUID | None
    created_at: datetime
    updated_at: datetime
    team_size: int
    # Student-specific fields
    is_current_user_leader: bool = False
    is_current_user_member: bool = False
    members: list[StudentTeamMemberData] | None = None


@dataclass
class StudentAvailableTeamData:
    """
    Data transfer object for teams available to join in a contest.

    Used for "GET /contests/{id}/teams/available" endpoint.
    Shows teams that student can join (have available slots).
    """

    id: UUID
    name: str
    description: str | None
    leader_name: str
    current_size: int
    max_size: int  # Max team size in contest
    available_slots: int  # current_size - max_size
    created_at: datetime


@dataclass
class StudentTeamRegistrationData:
    """
    Data transfer object for team registration in contest context.

    Tracks team participation status in a contest.
    """

    id: UUID
    name: str
    contest_id: UUID
    team_size: int
    enrolled_at: datetime
    team_status: TeamStatus
    approval_status: str  # TeamApprovalStatus: WAITING or APPROVED
    is_current_user_member: bool
    is_current_user_leader: bool


@dataclass
class StudentCreateTeamData:
    """
    Data transfer object for creating a team.

    Minimal data needed to create a team from student perspective.
    """

    name: str
    description: str | None
    contest_id: UUID  # Contest to register team in
    created_by: UUID  # Student creating the team


@dataclass
class StudentTeamJoinData:
    """
    Data transfer object for student joining an existing team.

    Represents action of student requesting/joining a team.
    """

    team_id: UUID
    contest_id: UUID
    user_id: UUID  # Student joining
    joined_at: datetime
    approval_status: str  # WAITING or APPROVED
