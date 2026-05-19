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
from app.exceptions.student.teams import StudentTeamNotFoundError, StudentTeamInvitationError
from app.core.guards.team_student import TeamStudentGuard
from app.mappers.student.team_mappers import (
    to_student_team_card_response,
    to_student_team_list_response,
    to_student_team_invitation_list_response,
)
from app.core.cache.decorators import cache_get, cache_delete
from app.utils.enums import TeamInvitationStatus, InvitationType


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
            f":is_public:{filters.is_public if filters.is_public is not None else 'all'}"
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

        pending_count = await self.repository.get_pending_student_invitations_count(
            user_id=user_id,
            invitation_type=InvitationType.INVITE,
            team_id=None,
        )

        requested_team_ids, pending_request_count = (
            await self.repository.get_user_pending_join_requests_data(user_id)
        )

        return to_student_team_list_response(
            teams=paginated_result.items,
            total=paginated_result.total,
            skip=pagination.skip,
            limit=pagination.limit,
            user_id=user_id,
            pending_invitation_count=pending_count,
            pending_request_count=pending_request_count,
            requested_team_ids=requested_team_ids,
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
        key_builder=lambda self, user_id, team_name, team_description, is_public=True: [
            f"student:teams:user:{user_id}:*",
            "student:teams:search:*",
            "student:teams:user:*"
        ]
    )
    async def create_student_team(
        self,
        user_id: UUID,
        team_name: str,
        team_description: str | None,
        is_public: bool = True,
    ) -> StudentTeamCardResponse:
        """Create a new team led by the student, invalidating list caches.

        Args:
            user_id: UUID of the student creating the team (becomes leader).
            team_name: Name of the team.
            team_description: Optional description of the team.
            is_public: Whether the team is public.

        Returns:
            StudentTeamCardResponse: Card details of the created team.
        """
        import random
        import string

        # Generate a unique 6-digit numeric code
        code = ""
        for _ in range(5):
            candidate = "".join(random.choices(string.digits, k=6))
            existing = await self.repository.get_team_by_code(candidate)
            if not existing:
                code = candidate
                break
        else:
            raise StudentTeamInvitationError("Could not generate a unique team code. Please try again.")

        team = Team(
            name=team_name,
            description=team_description,
            leader_id=user_id,
            created_by=user_id,
            is_public=is_public,
            code=code,
        )
        team = await self.repository.create_student_team(team)
        return to_student_team_card_response(team=team, user_id=user_id)

    @cache_delete(
        key_builder=lambda self, user_id, team_id: [
            f"student:teams:user:{user_id}:*",
            f"student:team:{team_id}:*",
            "student:teams:search:*",
            "student:teams:user:*"
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
        key_builder=lambda self, user_id, team_id, name, description, is_public=None: [
            f"student:teams:user:{user_id}:*",
            f"student:team:{team_id}:*",
            "student:teams:search:*",
            "student:teams:user:*"
        ]
    )
    async def update_student_team(
        self,
        user_id: UUID,
        team_id: UUID,
        name: str | None,
        description: str | None,
        is_public: bool | None = None,
    ) -> StudentTeamCardResponse:
        """Update an existing student team's details, validating leader privileges.

        Args:
            user_id: UUID of the requesting student user.
            team_id: UUID of the team to update.
            name: New name for the team (optional).
            description: New description for the team (optional).
            is_public: Updated public access setting (optional).

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
        if is_public is not None:
            team.is_public = is_public

        # Save to database
        updated_team = await self.repository.update_student_team(team)

        return to_student_team_card_response(team=updated_team, user_id=user_id)

    @cache_get(
        key_builder=lambda self, user_id, invitation_type, invitation_status=None, team_id=None, sent=False: (
            f"student:invitations:user:{user_id}"
            f":type:{invitation_type.value}"
            f":status:{invitation_status.value if invitation_status else 'all'}"
            f":team:{team_id if team_id else 'all'}"
            f":sent:{sent}"
        ),
        ttl=300,
    )
    async def get_team_invitations(
        self,
        user_id: UUID,
        invitation_type: InvitationType,
        invitation_status: TeamInvitationStatus | None = None,
        team_id: UUID | None = None,
        sent: bool = False,
    ) -> StudentTeamInvitationListResponse:
        """Retrieve the student's active team invitations or requests.

        Args:
            user_id: UUID of the requesting student user.
            invitation_type: The type of invitation (INVITE or REQUEST).
            invitation_status: Optional TeamInvitationStatus to filter by.
            team_id: Optional team ID to filter by.
            sent: Optional bool to retrieve sent invitations/requests.

        Returns:
            StudentTeamInvitationListResponse: List of mapped invitations/requests.
        """
        invitations = await self.repository.get_student_team_invitations(
            user_id=user_id,
            invitation_type=invitation_type,
            invitation_status=invitation_status,
            team_id=team_id,
            sent=sent,
        )

        return to_student_team_invitation_list_response(
            invitations=invitations,
            total=len(invitations),
        )

    @cache_delete(
        key_builder=lambda self, user_id, team_id, invitation_type, invite_user_id=None: [
            f"student:invitations:user:{invite_user_id or user_id}:*",
            f"student:teams:user:{invite_user_id or user_id}:*",
            "student:teams:search:*",
            "student:teams:user:*"
        ]
    )
    async def create_team_invitation(
        self,
        user_id: UUID,
        team_id: UUID,
        invitation_type: InvitationType,
        invite_user_id: UUID | None = None,
    ) -> None:
        """Create a team invitation or request."""
        if invitation_type == InvitationType.INVITE:
            if not invite_user_id:
                raise StudentTeamInvitationError("invite_user_id is required for INVITE type")
            # Check permission: Only team leader can invite a student
            team = await self.repository.get_student_team_by_id_or_raise(user_id, team_id)
            self.guard.check_is_leader(user_id=user_id, team=team)
            # Create the invitation
            await self.repository.create_student_team_invitation(
                team_id=team_id,
                sender_id=user_id,
                invitation_type=InvitationType.INVITE,
                reciever_id=invite_user_id,
            )
        elif invitation_type == InvitationType.REQUEST:
            await self.repository.create_student_team_invitation(
                team_id=team_id,
                sender_id=user_id,
                invitation_type=InvitationType.REQUEST,
                reciever_id=None,
            )

    @cache_delete(
        key_builder=lambda self, user_id, invitation_id, status: [
            f"student:invitations:user:{user_id}:*",
            f"student:teams:user:{user_id}:*",
            "student:teams:search:*",
            "student:teams:user:*"
        ]
    )
    async def update_team_invitation_status(self, user_id: UUID, invitation_id: UUID, status: TeamInvitationStatus)->None:
        team_invitation = await self.repository.get_student_team_invitation_or_raise(invitation_id)
        
        if status == TeamInvitationStatus.CANCELLED:
            if team_invitation.status != TeamInvitationStatus.PENDING:
                raise StudentTeamInvitationError("Only pending invitations or requests can be cancelled")
            if team_invitation.sender_id != user_id:
                raise StudentTeamInvitationError("Only the sender can cancel this invitation/request")
        elif team_invitation.invitation_type == InvitationType.INVITE:
            if team_invitation.reciever_id != user_id:
                raise StudentTeamInvitationError("You are not the receiver of this invitation")
        elif team_invitation.invitation_type == InvitationType.REQUEST:
            # Check permission: Only team leader can approve/reject request to join
            team = await self.repository.get_student_team_by_id_or_raise(user_id, team_invitation.team_id)
            self.guard.check_is_leader(user_id=user_id, team=team)
            
        await self.repository.update_team_invitation_status(team_invitation, status)
        return 

    @cache_delete(
        key_builder=lambda self, user_id, team_id, new_leader_id: [
            f"student:teams:user:{user_id}:*",
            f"student:teams:user:{new_leader_id}:*",
            f"student:team:{team_id}:*",
            "student:teams:search:*",
            "student:teams:user:*"
        ]
    )
    async def transfer_team_leader(self, user_id: UUID, team_id:UUID, new_leader_id: UUID)-> None:
        #Get the team enitity
        team = await self.repository.get_student_team_by_id_or_raise(user_id, team_id)

        #Check if user_id is the leader
        self.guard.check_is_leader(user_id=user_id, team=team)
        
        #Check if new_leader_id is a member of the team
        await self.guard.check_is_member(team_id=team_id, user_id=new_leader_id)

        #Update the leader
        team.leader_id = new_leader_id
        await self.repository.update_student_team(team)

    @cache_delete(
        key_builder=lambda self, user_id, team_id, leave_member_id: [
            f"student:teams:user:{user_id}:*",
            f"student:teams:user:{leave_member_id}:*",
            f"student:team:{team_id}:*",
            "student:teams:search:*",
            "student:teams:user:*"
        ]
    )
    async def leave_team(self, user_id:UUID, team_id:UUID, leave_member_id: UUID):
        
        #Get the team entity
        team = await self.repository.get_student_team_by_id_or_raise(user_id, team_id)

        if user_id != leave_member_id:
            self.guard.check_is_leader(user_id=user_id, team=team) 

        if team.leader_id == leave_member_id:
            #Transfer ownership if only two members are there
            members = team.members
            if(len(members) >= 2):
                next_member = [m for m in members if m.user_id != leave_member_id][0]
                team.leader_id = next_member.user_id
                await self.repository.update_student_team(team)
            else:
                raise StudentTeamInvitationError("Cannot leave team with only one member")
        
        await self.repository.leave_team(team_id, leave_member_id)

    @cache_get(
        key_builder=lambda self, name, pagination, user_id: (
            f"student:teams:search:{name}"
            f":skip:{pagination.skip}:limit:{pagination.limit}"
            f":user:{user_id}"
        ),
        ttl=300,
    )
    async def search_teams_by_name(
        self,
        name: str,
        pagination: PaginationParams,
        user_id: UUID,
    ) -> StudentTeamListResponse:
        """Search student teams by name and return mapped cards with pending invitation count.

        Args:
            name: The query string to search in team names.
            pagination: PaginationParams containing skip and limit.
            user_id: UUID of the requesting student user.

        Returns:
            StudentTeamListResponse: Mapped list of team cards with total count and pending count.
        """
        paginated_result = await self.repository.search_teams_by_name(
            name_query=name,
            pagination=pagination,
        )

        pending_count = await self.repository.get_pending_student_invitations_count(
            user_id=user_id,
            invitation_type=InvitationType.INVITE,
            team_id=None,
        )

        requested_team_ids, pending_request_count = (
            await self.repository.get_user_pending_join_requests_data(user_id)
        )

        return to_student_team_list_response(
            teams=paginated_result.items,
            total=paginated_result.total,
            skip=pagination.skip,
            limit=pagination.limit,
            user_id=user_id,
            pending_invitation_count=pending_count,
            pending_request_count=pending_request_count,
            requested_team_ids=requested_team_ids,
        )
        

        