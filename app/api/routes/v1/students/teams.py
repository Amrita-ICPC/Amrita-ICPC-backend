#TODO: Implement RBAC auth gaurd
from app.repositories.user import UserRepository
from app.schema.student import (
    StudentTeamCreateRequest,
    StudentTeamUpdateRequest,
    StudentTeamInvitationListResponse,
    StudentTeamsResponse,
    StudentTeamInvitationUpdateRequest,
    StudentTeamListResponse,
    StudentTeamTransferLeaderRequest,
    TeamMemberDetailResponse,
)
from datetime import datetime
from uuid import UUID
from typing import Optional, Literal
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user_id
from app.core.clients.database import get_db
from app.core.response import create_api_response
from app.repositories.student.team import StudentTeamRepository
from app.repositories.dto.student.teams import StudentTeamFilters
from app.repositories.dto.pagination import PaginationParams
from app.schema.base import APIResponse
from app.schema.student.teams import StudentTeamCardResponse
from app.service.student.team import StudentTeamService
from app.core.guards.team_student import TeamStudentGuard
from app.utils.pagination import get_pagination
from app.utils.enums import TeamInvitationStatus, InvitationType

router = APIRouter(tags=["Student - Teams"])


def get_student_team_service(db: AsyncSession = Depends(get_db)) -> StudentTeamService:
    """Provide StudentTeamService instance with request-scoped dependencies.

    Args:
        db: Async database session injected by FastAPI.

    Returns:
        Configured StudentTeamService instance.
    """
    repository = StudentTeamRepository(db)
    user_repository = UserRepository(db)
    guard = TeamStudentGuard(db)
    return StudentTeamService(repository,user_repository, guard)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[StudentTeamsResponse],
)
async def get_my_teams(
    request: Request,
    page: int = Query(1, ge=1, description="Current page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search by team name"),
    created_only: bool = Query(False, description="Filter only teams created by you"),
    leader_only: bool = Query(False, description="Filter only teams where you are the leader"),
    min_size: int | None = Query(None, description="Minimum team size filter"),
    max_size: int | None = Query(None, description="Maximum team size filter"),
    is_public: bool | None = Query(None, description="Filter by public/private setting"),
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[StudentTeamsResponse]:
    """Retrieve paginated and filtered list of teams that the student belongs to.

    Args:
        request: FastAPI Request object.
        page: Current page number.
        page_size: Items per page.
        search: Optional search term.
        created_only: Filter only created teams.
        leader_only: Filter only teams where you are the leader.
        min_size: Minimum team member size.
        max_size: Maximum team member size.
        is_public: Filter by public/private setting.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        API response containing team cards list and paginated metadata.
    """
    filters = StudentTeamFilters(
        search_term=search,
        created_only=created_only,
        leader_only=leader_only,
        min_size=min_size,
        max_size=max_size,
        is_public=is_public,
    )
    pagination = PaginationParams(
        skip=(page - 1) * page_size,
        limit=page_size,
    )

    list_response = await service.get_student_teams(
        user_id=user_id,
        filters=filters,
        pagination=pagination,
    )

    pagination_meta = get_pagination(
        total=list_response.total,
        page=page,
        page_size=page_size,
    )


    return create_api_response(
        request,
        data={
            "teams": list_response.teams,
            "pending_invitation": list_response.pending_invitation_count,
            "pending_request": list_response.pending_request_count,
        },
        message="Student teams fetched successfully",
        pagination=pagination_meta,
    )

@router.get(
    "/invitations",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[StudentTeamInvitationListResponse],
)
async def get_team_invitations(
    request: Request,
    invitation_type: InvitationType = Query(InvitationType.INVITE, alias="type", description="Type of invitation (INVITE or REQUEST)"),
    status_filter: Optional[TeamInvitationStatus] = Query(None, alias="status", description="Filter invitations by status"),
    team_id: Optional[UUID] = Query(None, alias="team_id", description="Optional team ID filter"),
    sent: bool = Query(False, alias="sent", description="Filter for sent invitations/requests where current user is the sender"),
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[StudentTeamInvitationListResponse]:
    """Retrieve all team invitations or requests for the authenticated student.

    Args:
        request: FastAPI Request object.
        invitation_type: Type of invitation filter.
        status_filter: Optional invitation status filter.
        team_id: Optional team ID filter.
        sent: Optional bool to retrieve sent invitations/requests.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        API response containing list of invitations/requests.
    """
    invitations = await service.get_team_invitations(
        user_id=user_id,
        invitation_type=invitation_type,
        invitation_status=status_filter,
        team_id=team_id,
        sent=sent,
    )
    return create_api_response(
        request,
        data=invitations,
        message="Team invitations fetched successfully",
    )

@router.patch(
    "/invitations/{id}",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[None],
)
async def update_team_invitation_status(
    request: Request,
    id: UUID,
    body: StudentTeamInvitationUpdateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[None]:
    """Update a team invitation status (accept, reject, or cancel).

    Args:
        request: FastAPI Request object.
        id: UUID of the target invitation.
        body: Request body containing the status.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        APIResponse indicating successful update.
    """
    await service.update_team_invitation_status(
        user_id=user_id, invitation_id=id, status=body.status
    )
    return create_api_response(
        request,
        data=None,
        message="Team invitation status updated successfully",
    )

@router.post(
    "/{team_id}/leader",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[None],
)
async def transfer_team_leadership(
    request: Request,
    team_id: UUID,
    body: StudentTeamTransferLeaderRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[None]:
    """Transfer team leadership to another member.

    Args:
        request: FastAPI Request object.
        team_id: UUID of the target team.
        body: Request body containing the new leader ID.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        APIResponse indicating successful leadership transfer.
    """
    await service.transfer_team_leader(
        user_id=user_id, team_id=team_id, new_leader_id=body.new_leader_id
    )
    return create_api_response(
        request,
        data=None,
        message="Team leadership transferred successfully",
    )


@router.delete(
    "/{team_id}/members/me",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[None],
)
async def leave_team_me(
    request: Request,
    team_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[None]:
    """Leave the team voluntarily (authenticated user leaves).

    Args:
        request: FastAPI Request object.
        team_id: UUID of the team.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        APIResponse indicating successful team exit.
    """
    await service.leave_team(
        user_id=user_id, team_id=team_id, leave_member_id=user_id
    )
    return create_api_response(
        request,
        data=None,
        message="Successfully left the team",
    )


@router.delete(
    "/{team_id}/members/{member_id}",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[None],
)
async def remove_team_member(
    request: Request,
    team_id: UUID,
    member_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[None]:
    """Remove/kick a member from the team. Only the team leader is permitted, or if it is me, the user leaves.

    Args:
        request: FastAPI Request object.
        team_id: UUID of the team.
        member_id: UUID of the member to remove.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        APIResponse indicating successful member removal.
    """
    await service.leave_team(
        user_id=user_id, team_id=team_id, leave_member_id=member_id
    )
    return create_api_response(
        request,
        data=None,
        message="Member successfully removed from the team",
    )


@router.get(
    "/search",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[StudentTeamListResponse],
)
async def search_teams_by_name(
    request: Request,
    name: str = Query(..., min_length=1, description="Search teams by name"),
    page: int = Query(1, ge=1, description="Current page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[StudentTeamListResponse]:
    """Search student teams by name with case-insensitive partial match.

    Args:
        request: FastAPI Request object.
        name: Name query to search.
        page: Current page number.
        page_size: Items per page.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        API response containing paginated list of matched student team cards.
    """
    pagination = PaginationParams(
        skip=(page - 1) * page_size,
        limit=page_size,
    )

    list_response = await service.search_teams_by_name(
        name=name,
        pagination=pagination,
        user_id=user_id,
    )

    pagination_meta = get_pagination(
        total=list_response.total,
        page=page,
        page_size=page_size,
    )

    return create_api_response(
        request,
        data=list_response,
        message="Teams searched successfully",
        pagination=pagination_meta,
    )


@router.get(
    "/{team_id}",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[StudentTeamCardResponse],
)
async def get_team_by_id(
    request: Request,
    team_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[StudentTeamCardResponse]:
    """Retrieve details of a specific team the student belongs to.

    Args:
        request: FastAPI Request object.
        team_id: UUID of the target team.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        API response containing team card details.

    Raises:
        AppBaseException: If the team is not found or student lacks permission.
    """
    team_card = await service.get_student_team_by_id(user_id=user_id, team_id=team_id)
    return create_api_response(
        request,
        data=team_card,
        message="Team details fetched successfully",
    )

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=APIResponse[StudentTeamCardResponse],
)
async def create_team(
    request: Request,
    team_create_request: StudentTeamCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[StudentTeamCardResponse]:
    """Create a new team led by the authenticated student.

    Args:
        request: FastAPI Request object.
        team_create_request: Request body with team details.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        API response containing the created team's card.
    """
    team_card = await service.create_student_team(
        user_id=user_id,
        team_name=team_create_request.name,
        team_description=team_create_request.description,
        is_public=team_create_request.is_public,
    )
    return create_api_response(
        request,
        data=team_card,
        message="Team created successfully",
    )


@router.delete(
    "/{team_id}",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[None],
)
async def delete_team(
    request: Request,
    team_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[None]:
    """Delete an existing student team. Only the team leader is permitted.

    Args:
        request: FastAPI Request object.
        team_id: UUID of the team to delete.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        API response indicating successful deletion.
    """
    await service.delete_student_team(user_id=user_id, team_id=team_id)
    return create_api_response(
        request,
        data=None,
        message="Team deleted successfully",
    )
    


@router.patch(
    "/{team_id}",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[StudentTeamCardResponse],
)
async def edit_team(
    request: Request,
    team_id: UUID,
    team_update_request: StudentTeamUpdateRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[StudentTeamCardResponse]:
    """Edit/Update an existing student team. Only the team leader is permitted.

    Args:
        request: FastAPI Request object.
        team_id: UUID of the team to edit/update.
        team_update_request: Request body with team details to update.
        user_id: ID of the authenticated user.
        service: Injected StudentTeamService.

    Returns:
        API response containing the updated team's card.
    """
    updated_card = await service.update_student_team(
        user_id=user_id,
        team_id=team_id,
        name=team_update_request.name,
        description=team_update_request.description,
        is_public=team_update_request.is_public,
    )
    return create_api_response(
        request,
        data=updated_card,
        message="Team updated successfully",
    )


@router.post(
    "/{team_id}/invitation/{invite_user_id}",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[None],
)
@router.post(
    "/{team_id}/invitation",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[None],
)
async def invite_to_team(
    request: Request,
    team_id: UUID,
    invite_user_id: Optional[UUID] = None,
    invitation_type: InvitationType = Query(InvitationType.INVITE, alias="type", description="Type of invitation (INVITE or REQUEST)"),
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[None]:
    """Invite a user to join the team (INVITE type) or request to join a team (REQUEST type)."""
    await service.create_team_invitation(
        user_id=user_id,
        team_id=team_id,
        invitation_type=invitation_type,
        invite_user_id=invite_user_id,
    )
    message = "Invitation sent successfully" if invitation_type == InvitationType.INVITE else "Request sent successfully"
    return create_api_response(
        request,
        data=None,
        message=message,
    )


@router.get(
    "/{team_id}/members",
    status_code=status.HTTP_200_OK,
    response_model=APIResponse[list[TeamMemberDetailResponse]],
    summary="Get details of all members in a team",
)
async def get_team_members(
    request: Request,
    team_id: UUID,
    name: Optional[str] = Query(None, description="Filter members by name"),
    email: Optional[str] = Query(None, description="Filter members by email"),
    joined_after: Optional[datetime] = Query(
        None, description="Filter members who joined after this timestamp"
    ),
    joined_before: Optional[datetime] = Query(
        None, description="Filter members who joined before this timestamp"
    ),
    sort_by: Literal["name", "email", "joined_at"] = Query(
        "joined_at", description="Field to sort members by"
    ),
    order: Literal["asc", "desc"] = Query(
        "asc", description="Sort order (asc or desc)"
    ),
    contest_id: Optional[UUID] = Query(
        None,
        description="Optional contest ID to check if team members are already registered in it",
    ),
    user_id: UUID = Depends(get_current_user_id),
    service: StudentTeamService = Depends(get_student_team_service),
) -> APIResponse[list[TeamMemberDetailResponse]]:
    """Retrieve detailed information of all members in the specified team.

    Optional filters for name, email, and joined_at timestamp are supported.
    Sorting/ordering is supported on name, email, and joined_at.
    If contest_id is provided, checks if each member is already registered in it.
    """
    members = await service.get_team_members(
        user_id=user_id,
        team_id=team_id,
        name_filter=name,
        email_filter=email,
        joined_after=joined_after,
        joined_before=joined_before,
        sort_by=sort_by,
        order=order,
        contest_id=contest_id,
    )
    return create_api_response(
        request,
        data=members,
        message="Team members fetched successfully",
    )







    