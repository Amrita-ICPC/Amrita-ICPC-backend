from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import TeamNotFoundError
from app.exceptions.user import UserNotFoundError
from app.models.contest import Contest, ContestTeam, ContestTeamProgress
from app.models.team import Team, TeamUser
from app.models.user import User
from app.utils.enums import TeamStatus


@dataclass
class CreateTeamData:
    """
    Data transfer object for creating teams in the repository layer.

    This class encapsulates the data needed to create a team without exposing
    the API schema (TeamCreate DTO) to the repository layer, maintaining
    separation of concerns.
    """

    contest_id: UUID
    name: str
    description: str | None
    logo: str | None
    leader_id: UUID
    member_ids: list[UUID]
    status: TeamStatus
    created_by: UUID


@dataclass
class UpdateTeamData:
    """
    Data transfer object for updating teams in the repository layer.

    This class encapsulates the data needed to update a team without exposing
    the API schema (TeamUpdate DTO) to the repository layer, maintaining
    separation of concerns.
    """

    team_id: UUID
    name: str | None = None
    description: str | None = None
    logo: str | None = None
    status: TeamStatus | None = None


class TeamRepository:
    """
    Repository for team-related database operations.

    This class provides methods to interact with the database for team management,
    including creating teams, adding/removing members, and retrieving team information.
    """

    def __init__(self, db: Session):
        self.db = db

    # contest team related operations
    def get_contest_or_raise(self, contest_id: UUID) -> Contest:
        """
        Retrieve a contest by its ID or raise an exception if not found.

        Args:
            contest_id: ID of the contest to retrieve.
        Returns:
            The Contest object if found.
        Raises:
            ContestNotFoundError: If the contest with the given ID does not exist.
        """
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(contest_id)
        return contest

    def get_user_or_raise(self, user_id: UUID) -> User:
        """
        Retrieve a user by their ID or raise an exception if not found.

        Args:
            user_id: ID of the user to retrieve.
        Returns:
            The User object if found.
        Raises:
            UserNotFoundError: If the user with the given ID does not exist.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError(user_id)
        return user

    def get_users_or_raise(self, user_ids: list[UUID]) -> list[User]:
        """
        Retrieve multiple users by their IDs or raise an exception if any are not found.

        Args:
            user_ids: List of user IDs to retrieve.
        Returns:
            List of User objects corresponding to the provided IDs.
        Raises:
            UserNotFoundError: If any user with the given IDs does not exist.
        """
        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        if len(users) != len(user_ids):
            found_user_ids = {user.id for user in users}
            missing_user_ids = set(user_ids) - found_user_ids
            raise UserNotFoundError(str(next(iter(missing_user_ids))))
        return users

    def find_team_by_name(self, contest_id: UUID, team_name: str) -> ContestTeam | None:
        """
        Find a team by its name within a specific contest.

        Args:
            contest_id: ID of the contest to search within.
            team_name: Name of the team to find.

        Returns:
            The ContestTeam object if found, otherwise None.
        """
        return (
            self.db.query(Team)
            .join(ContestTeam)
            .filter(
                ContestTeam.contest_id == contest_id,
                Team.name == team_name,
            )
            .first()
        )

    def get_contest_team_or_raise(self, contest_id: UUID, team_id: UUID) -> ContestTeam:
        """
        Retrieve a ContestTeam by contest ID and team ID or raise an exception if not found.

        Args:
            contest_id: ID of the contest.
            team_id: ID of the team.
        Returns:
            The ContestTeam object if found.
        Raises:
            TeamNotFoundError: If the ContestTeam with the given contest ID and team ID
            does not exist.
        """
        contest_team = (
            self.db.query(ContestTeam)
            .options(joinedload(ContestTeam.team))
            .filter(
                ContestTeam.contest_id == contest_id,
                ContestTeam.team_id == team_id,
            )
            .first()
        )
        if not contest_team:
            raise TeamNotFoundError(str(team_id), str(contest_id))
        return contest_team

    def get_team_members_or_raise(self, team_id: UUID) -> list[User]:
        """
        Retrieve the members of a team by team ID or raise an exception if not found.

        Args:
            team_id: ID of the team.
        Returns:
            List of User objects representing the team members.
        Raises:
            TeamNotFoundError: If the team with the given ID does not exist.
        """
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise TeamNotFoundError(str(team_id))
        members = (
            self.db.query(User)
            .join(TeamUser, TeamUser.user_id == User.id)
            .filter(TeamUser.team_id == team_id)
            .all()
        )
        return members

    def get_team_members_count_or_raise(self, team_id: UUID) -> int:
        """
        Retrieve the count of members in a team by team ID or raise an exception if not found.

        Args:
            team_id: ID of the team.
        Returns:
            The count of team members.
        Raises:
            TeamNotFoundError: If the team with the given ID does not exist.
        """
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise TeamNotFoundError(str(team_id))
        member_count = (
            self.db.query(TeamUser).filter(TeamUser.team_id == team_id).count()
        )
        return member_count

    def create_team(self, team_data: CreateTeamData) -> ContestTeam:
        """
        Create a new team in the database.

        Args:
            team_data: CreateTeamData object containing all team creation data

        Returns:
            The created ContestTeam object with its associated Team data loaded
        """
        team = Team(
            name=team_data.name,
            description=team_data.description,
            logo=team_data.logo,
            leader_id=team_data.leader_id,
            created_by=team_data.created_by,
        )
        self.db.add(team)
        self.db.flush()  # Flush to get the team ID

        contest_team = ContestTeam(
            contest_id=team_data.contest_id,
            team_id=team.id,
            team_status=team_data.status,
        )
        self.db.add(contest_team)

        progress = ContestTeamProgress(
            contest_id=team_data.contest_id,
            team_id=team.id,
        )

        self.db.add(progress)
        self.db.add_all(
            TeamUser(team_id=team.id, user_id=member_id)
            for member_id in team_data.member_ids
        )

        self.db.flush()  # Flush to save all changes and get IDs

        return (
            self.db.query(ContestTeam)
            .options(joinedload(ContestTeam.team))
            .filter(
                ContestTeam.team_id == team.id,
                ContestTeam.contest_id == team_data.contest_id,
            )
            .first()
        )

    def update_team(
        self, team_data: UpdateTeamData, team: Team, contest_team: ContestTeam
    ) -> ContestTeam:
        """
        Update an existing team in the database.

        Args:
            team: Team object with updated data (must have valid ID)

        Returns:
            The updated ContestTeam object with its associated Team data loaded
        """
        if team_data.name is not None and team_data.name != team.name:
            team.name = team_data.name
        if (
            team_data.description is not None
            and team_data.description != team.description
        ):
            team.description = team_data.description
        if team_data.logo is not None and team_data.logo != team.logo:
            team.logo = team_data.logo
        if (
            team_data.status is not None
            and team_data.status != contest_team.team_status
        ):
            contest_team.team_status = team_data.status

        self.db.flush()  # Flush to save changes

        return (
            self.db.query(ContestTeam)
            .options(joinedload(ContestTeam.team))
            .filter(
                ContestTeam.team_id == team.id,
                ContestTeam.contest_id == contest_team.contest_id,
            )
            .first()
        )
