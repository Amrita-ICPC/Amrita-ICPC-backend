from uuid import UUID

from sqlalchemy.orm import Session

from app.core.cache.decorators import cache_delete, cache_set
from app.core.permissions import ContestPermission, TeamPermission
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import InvalidTeamSizeError, TeamAlreadyExistsError
from app.exceptions.user import UserNotFoundError
from app.models.contest import (
    Contest,
    ContestTeam,
    ContestTeamProgress,
)
from app.models.team import Team, TeamUser
from app.models.user import User
from app.schema.team import TeamCreate, TeamResponse
from app.utils.enums import TeamStatus


def get_team_key(team_id: UUID) -> str:
    return f"team:{team_id}"


def get_contest_teams_key(contest_id: UUID) -> str:
    return f"contest:{contest_id}:teams"


class TeamService:
    """Service for team database operations."""

    def __init__(self, db: Session):
        self.db = db

    @cache_set(
        key_builder=lambda result, **kwargs: get_team_key(result.id), from_result=True
    )
    @cache_delete(
        key_builder=lambda self, contest_id, *args, **kwargs: get_contest_teams_key(
            contest_id
        )
    )
    async def create_team(
        self, contest_id: UUID, team_data: TeamCreate, created_by: UUID
    ) -> TeamResponse:
        """
        Create a new team in a contest.

        Args:
            contest_id: Contest ID
            team_data: Team creation data
            created_by: User ID creating the team (Instructor)

        Returns:
            Created team object

        Raises:
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user doesn't have permission
            TeamAlreadyExistsError: If team name already exists in contest
            InvalidTeamSizeError: If team size is invalid
            UserNotFoundError: If any member not found
        """
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(
            self.db, user_id=created_by, contest=contest
        )

        # check team name uniqueness in contest
        existing_team = (
            self.db.query(Team)
            .join(ContestTeam)
            .filter(ContestTeam.contest_id == contest_id, Team.name == team_data.name)
            .first()
        )
        if existing_team:
            raise TeamAlreadyExistsError(team_data.name, str(contest_id))

        # Validate team size
        num_members = len(team_data.member_ids)
        if num_members > contest.max_team_size:
            raise InvalidTeamSizeError(
                num_members, contest.min_team_size, contest.max_team_size
            )

        if team_data.status == TeamStatus.CONFIRMED:
            if num_members < contest.min_team_size:
                raise InvalidTeamSizeError(
                    num_members, contest.min_team_size, contest.max_team_size
                )

        # Validate members existence and permission
        for member_id in team_data.member_ids:
            user = self.db.query(User).filter(User.id == member_id).first()
            if not user:
                raise UserNotFoundError(str(member_id))
            TeamPermission.is_student_allowed_for_contest(
                self.db, user_id=member_id, contest_id=contest_id
            )

        # Validate leader existence if provided (already handled by schema validator, but good for safety)
        if team_data.leader_id:
            user = self.db.query(User).filter(User.id == team_data.leader_id).first()
            if not user:
                raise UserNotFoundError(str(team_data.leader_id))
            TeamPermission.is_student_allowed_for_contest(
                self.db, user_id=team_data.leader_id, contest_id=contest_id
            )

        # Create Team (independent of contest now)
        team = Team(
            name=team_data.name,
            description=team_data.description,
            logo=team_data.logo,
            created_by=created_by,
            leader_id=team_data.leader_id,
        )
        self.db.add(team)
        self.db.flush()  # Get team ID

        # Create ContestTeam (Link Team to Contest)
        contest_team = ContestTeam(
            contest_id=contest_id,
            team_id=team.id,
            team_status=team_data.status,
        )
        self.db.add(contest_team)

        # Create ContestTeamProgress
        progress = ContestTeamProgress(
            contest_id=contest_id,
            team_id=team.id,
        )
        self.db.add(progress)

        # Add members
        for member_id in team_data.member_ids:
            team_user = TeamUser(team_id=team.id, user_id=member_id)
            self.db.add(team_user)

        self.db.flush()
        self.db.refresh(team)
        return TeamResponse.model_validate(team)
