from uuid import UUID

from sqlalchemy.orm import Session

from app.core.cache.decorators import cache_delete, cache_get, cache_set
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
from app.schema.team import ContestTeamResponse, TeamCreate
from app.utils.enums import TeamStatus


def get_team_key(team_id: UUID) -> str:
    return f"team:{team_id}"


class TeamService:
    """Service for team database operations."""

    def __init__(self, db: Session):
        self.db = db

    @cache_set(
        key_builder=lambda result, **kwargs: get_team_key(result.id), from_result=True
    )
    @cache_delete(
        key_builder=lambda self,
        contest_id,
        *args,
        **kwargs: f"contest:{contest_id}:teams:*"
    )
    async def create_team(
        self, contest_id: UUID, team_data: TeamCreate, created_by: UUID
    ) -> ContestTeamResponse:
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
        self.db.refresh(contest_team)

        # Ensure the relationship is loaded properly
        contest_team_with_team = (
            self.db.query(ContestTeam)
            .join(Team)
            .filter(
                ContestTeam.contest_id == contest_id, ContestTeam.team_id == team.id
            )
            .first()
        )

        return ContestTeamResponse.from_contest_team(contest_team_with_team)

    @cache_get(
        key_builder=lambda self,
        contest_id,
        user_id,
        search_term=None,
        status=None,
        skip=0,
        limit=100: f"contest:{contest_id}:teams:user:{user_id}:search:{search_term}:status:{status}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_contest_teams(
        self,
        contest_id: UUID,
        user_id: UUID,
        search_term: str | None = None,
        status: TeamStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[ContestTeamResponse]]:
        """
        Get all teams in a contest with optional search and filtering.
        Checks for read permission on the contest.
        """
        # Check permission
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_read_contest(self.db, user_id=user_id, contest=contest)

        # Execute the query
        base_query = (
            self.db.query(ContestTeam)
            .join(Team, ContestTeam.team_id == Team.id)
            .filter(ContestTeam.contest_id == contest_id)
        )

        if search_term:
            base_query = base_query.filter(Team.name.ilike(f"%{search_term}%"))

        if status:
            base_query = base_query.filter(ContestTeam.team_status == status)

        total = base_query.count()
        contest_teams = base_query.offset(skip).limit(limit).all()

        from app.schema.team import ContestTeamResponse

        return total, [
            ContestTeamResponse.from_contest_team(ct) for ct in contest_teams
        ]

    @cache_get(
        key_builder=lambda self,
        contest_id,
        team_id,
        user_id: f"contest:{contest_id}:team:{team_id}:user:{user_id}",
        ttl=300,
    )
    async def get_team_by_id(
        self, contest_id: UUID, team_id: UUID, user_id: UUID
    ) -> ContestTeamResponse:
        """
        Get a specific team in a contest.
        Checks for read permission on the contest.
        """
        # Check permission
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_read_contest(self.db, user_id=user_id, contest=contest)

        # Get the team
        contest_team = (
            self.db.query(ContestTeam)
            .filter(
                ContestTeam.contest_id == contest_id, ContestTeam.team_id == team_id
            )
            .first()
        )

        if not contest_team:
            from app.exceptions.team import TeamNotFoundError

            raise TeamNotFoundError(str(team_id), str(contest_id))

        from app.schema.team import ContestTeamResponse

        return ContestTeamResponse.from_contest_team(contest_team)
