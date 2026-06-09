from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    TeamMemberRole,
    WorkspaceRole,
)


class ContestSessionStatus(BaseModel):
    """
    Schema representing the status of the current contest session.

    Attributes:
        already_started: Indicates if the contest session has already started.
        started_at: Timestamp when the session was started, if applicable.
        ended_at: Timestamp when the session was ended, if applicable.
    """

    already_started: bool = Field(
        ..., description="Indicates if the contest session has already started"
    )
    started_at: datetime | None = Field(
        None, description="Timestamp when the session was started"
    )
    ended_at: datetime | None = Field(
        None, description="Timestamp when the session was ended"
    )

    model_config = ConfigDict(from_attributes=True)


class ContestRuntimeDetails(BaseModel):
    """
    Schema representing the current runtime details of a contest.

    Attributes:
        effective_end_time: The effective end time of the contest for the team.
        remaining_seconds: Remaining seconds in the contest.
    """

    effective_end_time: datetime | None = Field(
        None, description="The effective end time of the contest for the team"
    )
    remaining_seconds: int = Field(..., description="Remaining seconds in the contest")

    model_config = ConfigDict(from_attributes=True)


class WorkspaceParticipant(BaseModel):
    """
    Schema representing a participant in the team's shared workspace.

    Attributes:
        user_id: The UUID of the participant.
        name: Name of the participant.
        avatar_url: URL to the participant's avatar image.
        role: The workspace role of the participant.
        team_role: The team role of the participant (LEADER or MEMBER).
        workspace_role: The workspace role of the participant (EDITOR or VIEWER).
        is_self: Indicates if this participant is the current requesting user.
        is_online: Indicates if the participant is currently online.
    """

    user_id: UUID = Field(..., description="The UUID of the participant")
    name: str = Field(..., description="Name of the participant")
    avatar_url: str | None = Field(
        None, description="URL to the participant's avatar image"
    )
    role: WorkspaceRole = Field(
        ..., description="The workspace role of the participant"
    )
    team_role: TeamMemberRole = Field(
        ..., description="The team role of the participant (LEADER or MEMBER)"
    )
    workspace_role: WorkspaceRole = Field(
        ..., description="The workspace role of the participant (EDITOR or VIEWER)"
    )
    is_self: bool = Field(
        ..., description="Indicates if this participant is the current user"
    )
    is_online: bool | None = Field(
        None, description="Indicates if the participant is currently online"
    )

    model_config = ConfigDict(from_attributes=True)


class WorkspaceDetails(BaseModel):
    """
    Schema representing the team's shared workspace state.

    Attributes:
        participants: List of participants in the workspace.
    """

    participants: list[WorkspaceParticipant] = Field(
        ..., description="List of participants in the workspace"
    )

    model_config = ConfigDict(from_attributes=True)


class TeamProgressDetails(BaseModel):
    """
    Schema representing the performance and progress metrics of a team.

    Attributes:
        extra_time_seconds: Amount of extra time granted to the team in seconds.
        has_extra_time: Indicates if the team has extra time.
    """

    extra_time_seconds: int = Field(
        ..., description="Amount of extra time granted to the team in seconds"
    )
    has_extra_time: bool = Field(
        ..., description="Indicates if the team has extra time"
    )

    model_config = ConfigDict(from_attributes=True)


class PermissionsDetails(BaseModel):
    """
    Schema representing actions the current user can perform in the contest context.

    Attributes:
        can_view: Indicates if the user can view the workspace.
        can_edit: Indicates if the user can edit code.
        can_submit: Indicates if the user can submit code.
        can_switch_editor: Indicates if the user can request or become the active editor.
    """

    can_view: bool = Field(
        ..., description="Indicates if the user can view the workspace"
    )
    can_edit: bool = Field(..., description="Indicates if the user can edit code")
    can_submit: bool = Field(..., description="Indicates if the user can submit code")
    can_switch_editor: bool = Field(
        ..., description="Indicates if the user can request or become the active editor"
    )

    model_config = ConfigDict(from_attributes=True)


class ContestTeamProgressResponse(BaseModel):
    """
    Schema representing the complete contest progress and workspace status of a team.

    Attributes:
        contest_id: The UUID of the contest.
        contest_team_id: The UUID of the contest team.
        session: Active session details.
        runtime: Current runtime and timer state.
        workspace: Workspace participant and collaboration state.
        team_progress: Current performance metrics.
        permissions: Permissions for the requesting user.
    """

    contest_id: UUID = Field(..., description="The UUID of the contest")
    contest_team_id: UUID = Field(..., description="The UUID of the contest team")
    evaluate_on_submit: bool = Field(
        ..., description="Whether to evaluate submissions immediately on submit"
    )
    session: ContestSessionStatus = Field(..., description="Active session details")
    runtime: ContestRuntimeDetails = Field(
        ..., description="Current runtime and timer state"
    )
    workspace: WorkspaceDetails = Field(
        ..., description="Workspace collaboration state"
    )
    team_progress: TeamProgressDetails = Field(
        ..., description="Current performance metrics"
    )
    permissions: PermissionsDetails = Field(
        ..., description="Permissions for the requesting user"
    )

    model_config = ConfigDict(from_attributes=True)
