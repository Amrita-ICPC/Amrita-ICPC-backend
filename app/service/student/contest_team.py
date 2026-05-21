from app.schema.student.contest_team import ContestTeamUpdate
from app.validators.contest import ContestValidator
from app.core.guards.contest_student import ContestStudentGuard
from app.repositories.contest import ContestRepository
from app.validators.team import TeamValidator
from app.core.guards.team_student import TeamStudentGuard
from app.repositories.student.team import StudentTeamRepository
from app.schema.team import ContestTeamImport
from uuid import UUID
from app.models import ContestTeam
from app.repositories.student.contest_team import ContestTeamRepository
from app.mappers.student.contest_mappers import to_contest_team, to_contest_team_members
from app.core.cache.decorators import cache_delete


class ContestTeamService:
    """Service class for managing contest teams (student-facing operations)."""

    def __init__(
        self,
        repository: ContestTeamRepository,
        team_repository: StudentTeamRepository,
        team_student_guard: TeamStudentGuard,
        contest_repository: ContestRepository,
        contest_student_guard: ContestStudentGuard,
    ) -> None:
        """Initialize the ContestTeamService with required dependencies.

        Args:
            repository: Repository for contest team database operations.
            team_repository: Repository for student teams.
            team_student_guard: Guard for validating student team permissions.
            contest_repository: Repository for contests.
            contest_student_guard: Guard for validating student contest access.
        """
        self.repository = repository
        self.team_repository = team_repository
        self.team_student_guard = team_student_guard
        self.contest_repository = contest_repository
        self.contest_student_guard = contest_student_guard

    @cache_delete(
        key_builder=lambda self, contest_id, contest_team_import, user_id: [
            f"student:contests:user:{uid}:*"
            for uid in contest_team_import.member_ids
        ] + [
            f"student:contest:user:{uid}:contest:{contest_id}"
            for uid in contest_team_import.member_ids
        ]
    )
    async def import_team(
        self,
        contest_id: UUID,
        contest_team_import: ContestTeamImport,
        user_id: UUID,
    ) -> None:
        """Import an existing student team and its members into a contest.

        Args:
            contest_id: UUID of the contest.
            contest_team_import: DTO containing team_id and member_ids.
            user_id: UUID of the student requesting the import.
        """
        # Fetch the team and contest
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

        ContestValidator.validate_registration_date_past(contest.registration_start,contest.registration_end)

        team = await self.team_repository.get_student_team_by_id_or_raise(user_id, contest_team_import.team_id)

        # Check if the user is leader
        self.team_student_guard.check_is_leader(team=team, user_id=user_id)
        
        existing_members_ids = set([team_user.user_id for team_user in team.members])

        TeamValidator.validate_members_in_team(
            team_name=team.name,
            existing_member_ids=existing_members_ids,
            member_ids_to_check=set(contest_team_import.member_ids),
        )

        #Check if the team is already in the contest
        await self.contest_student_guard.check_team_already_in_contest(
            team_id=team.id, 
            contest_id=contest_id
        )

        #Check if the student is already in the contest
        await self.contest_student_guard.check_student_already_in_contest(
            contest_id=contest_id, 
            user_ids=contest_team_import.member_ids
        )
        
        # Check the audiences of the members
        if not contest.is_public:
            await self.contest_student_guard.check_student_aduiences_for_contest(
                user_ids=contest_team_import.member_ids,
                contest_id=contest_id,
            )

        # Map and create ContestTeam
        contest_team = to_contest_team(
            contest_id=contest_id,
            team=team,
            contest=contest,
        )
        contest_team = await self.repository.create_contest_team(contest_team)

        # Map and create ContestTeamMembers
        contest_team_members = to_contest_team_members(
            contest_id=contest_id,
            contest_team_id=contest_team.id,
            member_ids=contest_team_import.member_ids,
            user_id=user_id,
        )
        await self.repository.create_contest_team_members(contest_team_members)

        return None

    async def update_contest_team(
        self, 
        contest_team_id: UUID, 
        contest_team_update: ContestTeamUpdate,
        user_id: UUID
    ) -> None:
    
        # Fetch the contest team
        contest_team = await self.repository.get_contest_team_by_id_or_raise(contest_team_id)

        #Check if the user is leader
        self.team_student_guard.check_is_leader(team=contest_team.team, user_id=user_id)

        #update the name
        contest_team.name = contest_team_update.name
        
        await self.repository.update_contest_team(contest_team)

        return None
