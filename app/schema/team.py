from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from sqlalchemy import inspect

from app.utils.enums import (
    QuestionDifficulty,
    SubmissionStatus,
    TeamApprovalStatus,
    TeamStatus,
)


class TeamCreate(BaseModel):
    """
    Schema for creating a new team.

    Attributes:
        name: Name of the team.
        description: Description of the team.
        logo: URL or path to the team logo.
        member_ids: List of user IDs to include in the team.
        status: Status of the team (default: DRAFT).

    """

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    logo: Optional[str] = None
    member_ids: List[UUID] = Field(default_factory=list)
    leader_id: Optional[UUID] = None
    status: TeamStatus = Field(default=TeamStatus.DRAFT)
    # @model_validator(mode="after")
    # def validate_leader(self) -> "TeamCreate":
    #     member_ids = self.member_ids
    #     leader_id = self.leader_id

    #     if member_ids and leader_id is None:
    #         raise ValueError("Leader ID is required when there are members.")

    #     if leader_id and leader_id not in member_ids:
    #         raise ValueError("Leader must be one of the members.")

    #     return self


class TeamUpdate(BaseModel):
    """
    Schema for updating an existing team.

    Only allows updating basic team information.
    Members management should be handled through separate endpoints.

    Attributes:
        name: Updated name of the team.
        description: Updated description of the team.
        logo: Updated URL or path to the team logo.
        status: Updated status of the team in the contest.
        leader_id: Updated leader ID for the team.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    logo: Optional[str] = None
    status: Optional[TeamStatus] = None
    leader_id: Optional[UUID] = None


class TeamResponse(BaseModel):
    """
    Schema for team response.

    Attributes:
        id: Unique identifier for the team.
        name: Name of the team.
        description: Description of the team.
        logo: Team logo.
        status: Status of the team.
        leader_id: ID of the team leader.
        created_by: ID of the user who created the team.
        created_at: Timestamp when the team was created.
        updated_at: Timestamp when the team was last updated.
    """

    id: UUID
    name: str
    description: Optional[str]
    logo: Optional[str]
    status: TeamStatus
    leader_id: Optional[UUID]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamMemberPreview(BaseModel):
    """
    Schema for a minimal team member preview.
    """

    id: UUID
    name: str
    avatar: Optional[str] = None
    initials: str


class ParentTeamInfo(BaseModel):
    """
    Schema for basic information about the parent team.
    """

    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class ContestTeamResponse(BaseModel):
    """
    Schema for contest team response without member details.
    Used for team listings and basic team information.

    Attributes:
        id: Unique identifier for the team.
        name: Name of the team.
        status: Status of the team in the contest.
        approval_status: Approval status of the team.
        leader_id: ID of the team leader.
        enrolled_at: Timestamp when the team enrolled.
        members_preview: List of first 3 members for display.
        extra_members_count: Number of members beyond the preview.
        parent_team: Basic information about the parent team.
    """

    id: UUID
    name: str
    status: TeamStatus
    approval_status: TeamApprovalStatus
    leader_id: Optional[UUID]
    enrolled_at: datetime = Field(default_factory=datetime.now)
    members_preview: List[TeamMemberPreview] = Field(default_factory=list)
    extra_members_count: int = 0
    parent_team: Optional[ParentTeamInfo] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_contest_team(cls, contest_team, members=None) -> "ContestTeamResponse":
        """
        Create ContestTeamResponse from ContestTeam ORM object.

        Args:
            contest_team: ContestTeam ORM object
            members: Optional custom list of ContestTeamMember objects

        Returns:
            ContestTeamResponse with basic team data and member previews.
        """
        members_preview = []
        extra_count = 0
        parent_team_info = None

        if members is None:
            if "contest_team_member" in inspect(contest_team).unloaded:
                raise ValueError("Contest team members must be preloaded")
            members = contest_team.contest_team_member

        if contest_team.team:
            parent_team_info = ParentTeamInfo(
                id=contest_team.team.id, name=contest_team.team.name
            )

        # Safely handle members if loaded
        if members:
            # First 3 members only
            for team_member in members[:3]:
                user = team_member.user
                # Calculate initials (e.g., "John Doe" -> "JD")
                names = user.name.split()
                initials = "".join([n[0].upper() for n in names[:2]]) if names else ""

                members_preview.append(
                    TeamMemberPreview(
                        id=user.id,
                        name=user.name,
                        avatar=None,  # Not available in current User model
                        initials=initials,
                    )
                )

            if len(members) > 3:
                extra_count = len(members) - 3

        return cls(
            id=contest_team.id,
            name=contest_team.name,
            status=contest_team.team_status,
            approval_status=contest_team.approval_status,
            leader_id=contest_team.leader_id,
            enrolled_at=contest_team.enrolled_at,
            members_preview=members_preview,
            extra_members_count=extra_count,
            parent_team=parent_team_info,
        )


class TeamMemberResponse(BaseModel):
    """
    Schema for team member response.

    Represents a user who is part of a team with essential information.

    Attributes:
        id: Unique identifier for the user.
        user_id: External user identifier (e.g., student ID).
        name: Full name of the user.
        email: Email address of the user.
        role: Role of the user in the system.
        is_leader: Whether this member is the team leader.
    """

    id: UUID
    user_id: str
    name: str
    email: str
    role: str
    is_leader: bool = False

    model_config = ConfigDict(from_attributes=True)


class ContestTeamDetailResponse(TeamResponse):
    """
    Detailed schema for team response within a contest context.

    Attributes:
        status: Status of the team in the contest.
        members: List of team members.
        leader_id: ID of the team leader.
        created_by: ID of the user who created the team.
        created_at: Timestamp when the team was created.
        updated_at: Timestamp when the team was last updated.
    """

    status: TeamStatus
    approval_status: TeamApprovalStatus
    members: List[TeamMemberResponse]
    leader_id: Optional[UUID]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_contest_team(cls, contest_team) -> "ContestTeamDetailResponse":
        """
        Create ContestTeamDetailResponse from ContestTeam ORM object.

        Args:
            contest_team: ContestTeam ORM object

        Returns:
            ContestTeamDetailResponse with mapped data
        """
        team = contest_team.team

        # Map members
        members = [
            TeamMemberResponse(
                id=member.user.id,
                user_id=member.user.user_id,
                name=member.user.name,
                email=member.user.email,
                role=member.user.role.value,
                is_leader=(team.leader_id == member.user.id),
            )
            for member in team.members
        ]

        return cls(
            id=team.id,
            name=team.name,
            description=team.description,
            logo=team.logo,
            status=contest_team.team_status,
            approval_status=contest_team.approval_status,
            members=members,
            leader_id=team.leader_id,
            created_by=team.created_by,
            created_at=team.created_at,
            updated_at=team.updated_at,
        )


class TeamMemberAdd(BaseModel):
    """
    Schema for adding members to a team.

    Attributes:
        member_ids: List of user IDs to add to the team.
        leader_id: Optional new leader ID (must be one of the members).
    """

    member_ids: List[UUID] = Field(
        ..., min_length=1, description="List of user IDs to add"
    )
    leader_id: Optional[UUID] = Field(
        None, description="New team leader (must be existing or new member)"
    )

    @model_validator(mode="after")
    def validate_leader_in_members(self) -> "TeamMemberAdd":
        if self.leader_id and self.leader_id not in self.member_ids:
            raise ValueError("Leader must be one of the members being added")
        return self


class TeamMemberRemove(BaseModel):
    """
    Schema for removing members from a team.

    Attributes:
        member_ids: List of user IDs to remove from the team.
        new_leader_id: Optional new leader if removing current leader.
    """

    member_ids: List[UUID] = Field(
        ..., min_length=1, description="List of user IDs to remove from team"
    )
    new_leader_id: Optional[UUID] = Field(
        None, description="New leader if removing current leader"
    )


class TeamStatusCounts(BaseModel):
    """
    Schema for team status counts in a contest.
    """

    approved_count: int = 0
    waiting_count: int = 0
    rejected_count: int = 0
    disqualified_count: int = 0


class TeamListResponse(BaseModel):
    """
    Schema for paginated team list with status counts.
    """

    total: int
    teams: List[ContestTeamResponse]
    approved_count: int = 0
    waiting_count: int = 0
    rejected_count: int = 0
    disqualified_count: int = 0


class ContestTeamCreate(BaseModel):
    """
    Schema for creating a new contest team from scratch.

    Attributes:
        name: Name of the team.
        leader_id: Optional leader ID for the team.
        team_status: Status of the team in the contest (default: DRAFT).
    """

    name: str = Field(
        ..., min_length=1, max_length=100, description="Name of the team."
    )
    leader_id: Optional[UUID] = Field(None, description="Leader ID for the team.")
    team_status: TeamStatus = Field(
        default=TeamStatus.DRAFT, description="Status of the team in the contest."
    )

    model_config = ConfigDict(from_attributes=True)


class ContestTeamImport(BaseModel):
    """
    Schema for importing an existing team and its members into a contest.

    Attributes:
        team_id: UUID of the existing team to import.
        member_ids: List of user IDs of the members to be imported.
    """

    team_id: UUID = Field(..., description="UUID of the existing team to import.")
    member_ids: List[UUID] = Field(
        default_factory=list,
        description="List of user IDs representing the members of the team.",
    )

    model_config = ConfigDict(from_attributes=True)


class ContestTeamMemberAnalytics(BaseModel):
    id: UUID
    contest_team_member_id: UUID
    name: str
    email: str
    score: int = 0
    is_flagged: bool = False
    flagged_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    is_participated: bool = False
    is_leader: bool = False


class ContestTeamAnalytics(BaseModel):
    contest_team_id: UUID
    name: str
    score: int = 0
    members: List[ContestTeamMemberAnalytics] = Field(default_factory=list)
    total_submissions: int = 0
    accepted_submission: int = 0
    wrong_answer: int = 0
    time_limit_exceeded: int = 0
    runtime_error: int = 0
    compilation_error: int = 0
    memory_limit_exceeded: int = 0
    system_error: int = 0
    pending_submission: int = 0


class ContestTeamMemberQuestionAnalytics(BaseModel):
    question_id: UUID
    title: str
    difficulty: QuestionDifficulty
    time_limit_ms: int
    memory_limit_mb: int
    total_submission: int = 0
    accepted_submission: int = 0


class ContestTeamMemberSubmissionStatistics(BaseModel):
    total: int = 0
    accepted: int = 0
    wrong_answer: int = 0
    time_limit_exceeded: int = 0
    runtime_error: int = 0
    memory_limit_exceeded: int = 0
    compilation_error: int = 0
    system_error: int = 0
    pending: int = 0


class ContestTeamMemberQuestionStatistics(BaseModel):
    attempted: int = 0
    solved: int = 0
    unsolved: int = 0


class ContestTeamMemberDetail(BaseModel):
    contest_team_member_id: UUID
    user_id: UUID
    name: str
    email: str
    is_leader: bool = False
    is_participated: bool = False
    score: int = 0
    started_at: Optional[datetime] = None
    base_end_time: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    extra_time_seconds: int = 0
    remaining_time_seconds: int = 0
    is_flagged: bool = False
    flagged_at: Optional[datetime] = None
    flagged_reason: Optional[str] = None
    submission_statistics: ContestTeamMemberSubmissionStatistics = Field(
        default_factory=ContestTeamMemberSubmissionStatistics
    )
    question_statistics: ContestTeamMemberQuestionStatistics = Field(
        default_factory=ContestTeamMemberQuestionStatistics
    )


class ContestTeamMemberQuestionSubmissionStatistics(BaseModel):
    total: int = 0
    accepted: int = 0
    wrong_answer: int = 0
    time_limit_exceeded: int = 0
    runtime_error: int = 0
    compilation_error: int = 0


class ContestTeamMemberQuestionSubmissionItem(BaseModel):
    submission_id: UUID
    status: Optional[SubmissionStatus] = None
    score: int = 0
    language: str
    created_at: datetime
    execution_time: Optional[int] = None
    memory: Optional[int] = None


class ContestTeamMemberQuestionSubmissions(BaseModel):
    question_id: UUID
    question_title: str
    statistics: ContestTeamMemberQuestionSubmissionStatistics = Field(
        default_factory=ContestTeamMemberQuestionSubmissionStatistics
    )
    submissions: List[ContestTeamMemberQuestionSubmissionItem] = Field(
        default_factory=list
    )
