from app.repositories.user import UserRepository
from app.models.team import TeamInvitation
from uuid import UUID

from app.models import Team
from app.repositories.student.team import StudentTeamRepository
from app.repositories.dto.student.teams import StudentTeamFilters
from app.repositories.dto.pagination import PaginationParams
from app.schema.student.teams import (
    StudentTeamCardResponse,
    StudentTeamListResponse,
    StudentTeamInvitationListResponse,
)
from app.exceptions.base import AppBaseException
from app.exceptions.student.teams import StudentTeamNotFoundError
from app.core.guards.team_student import TeamStudentGuard
from app.mappers.student.team_mappers import (
    to_student_team_card_response,
    to_student_team_list_response,
    to_student_team_invitation_list_response,
)
from app.core.cache.decorators import cache_get, cache_delete
from app.utils.enums import TeamInvitationStatus


class StudentTeamService:
    """Service class for handling student-facing team operations.

    This service coordinates repository access, delegates DTO/schema
    mapping transformations, and validates leader rights using guards.
    """

    def __init__(
        self,
        repository: StudentTeamRepository,
        user_repository: UserRepository,
        guard: TeamStudentGuard,
    ) -> None:
        """Initialize the StudentTeamService with required dependencies.

        Args:
            repository: Repository for student team queries.
            user_repository: Repository for user queries.
            guard: Guard for validating student team permissions.
        """
        self.repository = repository
        self.guard = guard
        self.user_repository = user_repository

    @cache_get(
        key_builder=lambda self, user_id, filters, pagination: (
            f"student:teams:user:{user_id}"
            f":search:{filters.search_term or 'none'}"
            f":created:{filters.created_only}"
            f":leader:{filters.leader_only}"
            f":min:{filters.min_size or 'none'}"
            f":max:{filters.max_size or 'none'}"
            f":skip:{pagination.skip}:limit:{pagination.limit}"
        ),
        ttl=300,
    )
    async def get_student_teams(
        self,
        user_id: UUID,
        filters: StudentTeamFilters,
        pagination: PaginationParams,
    ) -> StudentTeamListResponse:
        """Retrieve paginated and filtered list of teams for a student.

        Args:
            user_id: UUID of the requesting student user.
            filters: StudentTeamFilters containing search, creation, and size parameters.
            pagination: PaginationParams containing skip and limit values.

        Returns:
            StudentTeamListResponse: Paginated list of team cards with total count metadata.
        """
        paginated_result = await self.repository.get_student_teams(
            user_id=user_id, filters=filters, pagination=pagination
        )

        pending_count = await self.repository.get_pending_student_invitations_count(user_id=user_id)

        return to_student_team_list_response(
            teams=paginated_result.items,
            total=paginated_result.total,
            skip=pagination.skip,
            limit=pagination.limit,
            user_id=user_id,
            pending_invitation_count=pending_count,
        )


    @cache_get(
        key_builder=lambda self, user_id, team_id: f"student:team:{team_id}:user:{user_id}",
        ttl=300,
    )
    async def get_student_team_by_id(
        self, user_id: UUID, team_id: UUID
    ) -> StudentTeamCardResponse:
        """Retrieve a specific team by its ID, validating that the student is a member.

        Args:
            user_id: UUID of the student user requesting the team.
            team_id: UUID of the team to retrieve.

        Returns:
            StudentTeamCardResponse: Details of the requested team.

        Raises:
            AppBaseException: If the team is not found or the user is not a member.
        """
        team = await self.repository.get_student_team_by_id_or_raise(
            user_id=user_id, team_id=team_id
        )
        if not team:
            raise AppBaseException(
                message=f"Team {team_id} not found or you do not have permission to view it.",
                status_code=404,
                detail=f"Team {team_id} not found or accessible.",
            )

        return to_student_team_card_response(team=team, user_id=user_id)

    @cache_delete(
        key_builder=lambda self, user_id, team_name, team_description: [
            f"student:teams:user:{user_id}:*"
        ]
    )
    async def create_student_team(
        self, user_id: UUID, team_name: str, team_description: str | None
    ) -> StudentTeamCardResponse:
        """Create a new team led by the student, invalidating list caches.

        Args:
            user_id: UUID of the student creating the team (becomes leader).
            team_name: Name of the team.
            team_description: Optional description of the team.

        Returns:
            StudentTeamCardResponse: Card details of the created team.
        """
        team = Team(
            name=team_name,
            description=team_description,
            leader_id=user_id,
            created_by=user_id,
        )
        team = await self.repository.create_student_team(team)
        return to_student_team_card_response(team=team, user_id=user_id)

    @cache_delete(
        key_builder=lambda self, user_id, team_id: [
            f"student:teams:user:{user_id}:*",
            f"student:team:{team_id}:*",
        ]
    )
    async def delete_student_team(self, user_id: UUID, team_id: UUID) -> None:
        """Delete an existing student team, validating that the requesting user is the leader.

        Args:
            user_id: UUID of the requesting student user.
            team_id: UUID of the team to delete.

        Raises:
            StudentTeamNotFoundError: If the team is not found or accessible.
            TeamLeaderAccessDeniedError: If the student is not the team leader.
        """
        # Retrieve the team to check ownership (raises StudentTeamNotFoundError if not found)
        team = await self.repository.get_student_team_by_id_or_raise(
            user_id=user_id, team_id=team_id
        )

        # Enforce leader restriction using guard
        self.guard.check_is_leader(user_id=user_id, team=team)

        # Perform deletion
        await self.repository.delete_student_team(team_id=team_id)

    @cache_delete(
        key_builder=lambda self, user_id, team_id, name, description: [
            f"student:teams:user:{user_id}:*",
            f"student:team:{team_id}:*",
        ]
    )
    async def update_student_team(
        self,
        user_id: UUID,
        team_id: UUID,
        name: str | None,
        description: str | None,
    ) -> StudentTeamCardResponse:
        """Update an existing student team's details, validating leader privileges.

        Args:
            user_id: UUID of the requesting student user.
            team_id: UUID of the team to update.
            name: New name for the team (optional).
            description: New description for the team (optional).

        Returns:
            StudentTeamCardResponse: Card details of the updated team.

        Raises:
            StudentTeamNotFoundError: If the team is not found or accessible.
            TeamLeaderAccessDeniedError: If the student is not the team leader.
        """
        # Retrieve the team to check ownership/permissions (raises StudentTeamNotFoundError if missing)
        team = await self.repository.get_student_team_by_id_or_raise(
            user_id=user_id, team_id=team_id
        )

        # Enforce leader restriction using guard
        self.guard.check_is_leader(user_id=user_id, team=team)

        # Apply updates if provided
        if name is not None:
            team.name = name
        if description is not None:
            team.description = description

        # Save to database
        updated_team = await self.repository.update_student_team(team)

        return to_student_team_card_response(team=updated_team, user_id=user_id)

    @cache_get(
        key_builder=lambda self, user_id, invitation_status=None: (
            f"student:invitations:user:{user_id}"
            f":status:{invitation_status.value if invitation_status else 'all'}"
        ),
        ttl=300,
    )
    async def get_team_invitations(
        self,
        user_id: UUID,
        invitation_status: TeamInvitationStatus | None = None,
    ) -> StudentTeamInvitationListResponse:
        """Retrieve the student's active team invitations.

        Args:
            user_id: UUID of the requesting student user.
            invitation_status: Optional TeamInvitationStatus to filter by.

        Returns:
            StudentTeamInvitationListResponse: List of mapped invitations.
        """
        invitations = await self.repository.get_student_team_invitations(
            user_id=user_id,
            invitation_status=invitation_status,
        )

        return to_student_team_invitation_list_response(
            invitations=invitations,
            total=len(invitations),
        )

    @cache_delete(
        key_builder=lambda self, user_id, team_id, invite_user_id: [
            f"student:invitations:user:{invite_user_id}:*",
            f"student:teams:user:{invite_user_id}:*",
        ]
    )
    async def create_team_invitations(self, user_id: UUID, team_id: UUID, invite_user_id: UUID):
        #Check the permission
        team = await self.repository.get_student_team_by_id_or_raise(user_id, team_id)
        self.guard.check_is_leader(user_id=user_id, team=team)
        await self.user_repository.get_user_or_raise(user_id=invite_user_id)
        await self.user_repository.get_user_or_raise(user_id=user_id)
        #Create the invitation
        await self.repository.create_student_team_invitation(team_id, invite_user_id, user_id)

    @cache_delete(
        key_builder=lambda self, user_id, invitation_id, status: [
            f"student:invitations:user:{user_id}:*",
            f"student:teams:user:{invitation_id}:*",
        ]
    )
    async def accept_or_reject_team_invitation(self, user_id: UUID, invitation_id: UUID, status: TeamInvitationStatus):
        team_invitation = await self.repository.get_student_team_invitation_or_raise(user_id, invitation_id)
        await self.repository.approve_or_reject_team_invitation(team_invitation, status)
        return 
        

        