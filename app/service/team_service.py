from uuid import UUID
from typing import List
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.core.logger import logger
from app.core.permissions import ContestPermission
from app.models.team import Team, TeamUser
from app.models.user import User
from app.models.contest import Contest
from app.schema.team import (
    TeamCreate, TeamUpdate, TeamResponse, 
    AddTeamMemberResponse, RemoveTeamMemberResponse, UserTeamResponse
)
from app.exceptions.team import (
    TeamNotFoundError, UserNotFoundError, 
    UserAlreadyInTeamError, UserNotInTeamError
)
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.base import AppBaseException
from app.core.cache.decorators import cache_delete, cache_get, cache_set


class TeamService:
    """Services for team database operation"""

    def __init__(self, db: Session):
        self.db = db

    @cache_delete(
        key_builder=lambda self, team_data, contest_id, user_id: "teams:list:*",
    )
    async def create_team(self, team_data: TeamCreate, contest_id: UUID, user_id: UUID) -> TeamResponse:
        """
        Create a new team within a contest.

        Args:
            team_data: Team creation data
            contest_id: Contest ID that team belongs to
            user_id: User ID creating the team (for permission check)

        Returns:
            Created Team object
        """
        try:
            # Verify contest exists
            contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
            if not contest:
                raise ContestNotFoundError(str(contest_id))
            
            # Check if user has permission to manage this contest
            # This will raise PermissionDeniedError if user doesn't have permission
            ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)
            
            team = Team(
                name=team_data.name,
                description=team_data.description,
                logo=team_data.logo,
                contest_id=contest_id
            )
            self.db.add(team)
            self.db.flush()
            self.db.refresh(team)
            logger.info(f"Team created successfully in contest {contest_id}: {team.id}")
            return TeamResponse.model_validate(team)
        
        except (ContestNotFoundError, PermissionDeniedError):
            self.db.rollback()
            raise
        
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Integrity error creating team: {str(e)}")
            raise AppBaseException("Team with this name already exists in contest", status_code=409)
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Unexpected error creating team: {str(e)}")
            raise AppBaseException("Failed to create team", status_code=500)

    @cache_get(
        key_builder=lambda self, team_id, contest_id: f"team:{team_id}:contest:{contest_id}",
        ttl=300,
    )
    async def get_team_by_id(self, team_id: UUID, contest_id: UUID) -> TeamResponse:
        """
        Get a team by its ID with required contest validation.

        Args:
            team_id: Team ID
            contest_id: Contest ID (required for validation)

        Returns:
            Team object
            
        Raises:
            TeamNotFoundError: If team not found or doesn't belong to contest
        """
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise TeamNotFoundError(str(team_id))
        
        # Validate team belongs to this contest
        if team.contest_id != contest_id:
            raise TeamNotFoundError(str(team_id))
        
        return TeamResponse.model_validate(team)
    
    @cache_get(
        key_builder=lambda self, contest_id, skip=0, limit=100: f"teams:contest:{contest_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_contest_teams(self, contest_id: UUID, skip: int = 0, limit: int = 100) -> tuple[int, List[TeamResponse]]:
        """
        Get all teams in a specific contest with pagination.

        Args:
            contest_id: Contest ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, teams list)
        """
        base_query = self.db.query(Team).filter(Team.contest_id == contest_id)
        total = base_query.count()
        teams = base_query.offset(skip).limit(limit).all()
        return total, [TeamResponse.model_validate(team) for team in teams]
    
    @cache_get(
        key_builder=lambda self, user_id, contest_id, skip=0, limit=100: f"teams:user:{user_id}:contest:{contest_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_user_teams(self, user_id: UUID, contest_id: UUID, skip: int = 0, limit: int = 100) -> tuple[int, List[TeamResponse]]:
        """
        Get all teams for a specific user in a specific contest with pagination.

        Args:
            user_id: User ID
            contest_id: Contest ID to filter teams (required)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, teams list)
        """
        base_query = (
            self.db.query(Team)
            .join(TeamUser)
            .filter(TeamUser.user_id == user_id)
            .filter(Team.contest_id == contest_id)
            .distinct()
        )
        
        total = base_query.count()
        teams = base_query.offset(skip).limit(limit).all()
        return total, [TeamResponse.model_validate(team) for team in teams]
    
    @cache_delete(
        key_builder=lambda self, team_id, team_data, contest_id, user_id: [
            "teams:list:*",
            "teams:user:*",
            f"team:{team_id}:members"
        ],
    )
    async def update_team(self, team_id: UUID, team_data: TeamUpdate, contest_id: UUID, user_id: UUID) -> TeamResponse:
        """
        Update a team within a contest.

        Args:
            team_id: Team ID
            team_data: Team update data
            contest_id: Contest ID (for validation)
            user_id: User ID updating the team (for permission check)

        Returns:
            Updated Team object
            
        Raises:
            TeamNotFoundError: If team not found or doesn't belong to contest
            PermissionDeniedError: If user lacks permission to manage contest
        """
        try:
            # Verify contest exists and user has permission
            contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
            if not contest:
                raise ContestNotFoundError(str(contest_id))
            
            # This will raise PermissionDeniedError if user doesn't have permission
            ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)
            
            # Note: We must fetch from DB directly here to modify it
            team = self.db.query(Team).filter(Team.id == team_id).first()
            if not team:
                 raise TeamNotFoundError(str(team_id))
            
            # Verify team belongs to this contest
            if team.contest_id != contest_id:
                raise TeamNotFoundError(str(team_id))

            update_data = team_data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(team, field, value)
            
            self.db.flush()
            self.db.refresh(team)
            logger.info("Team updated successfully")
            return TeamResponse.model_validate(team)
        
        except (ContestNotFoundError, TeamNotFoundError, PermissionDeniedError):
            self.db.rollback()
            raise
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating team: {str(e)}")
            raise AppBaseException("Failed to update team", status_code=500)

    @cache_delete(
        key_builder=lambda self, team_id, contest_id, user_id: [
            f"team:{team_id}",
            f"team:{team_id}:members",
            "teams:list:*",
            "teams:user:*",
        ]
    )
    async def delete_team(self, team_id: UUID, contest_id: UUID, user_id: UUID) -> TeamResponse:
        """
        Delete a team from a contest.

        Args:
            team_id: Team ID
            contest_id: Contest ID (for validation)
            user_id: User ID deleting the team (for permission check)

        Returns:
            Deleted team object
            
        Raises:
            TeamNotFoundError: If team not found or doesn't belong to contest
            PermissionDeniedError: If user lacks permission to manage contest
        """
        try:
            # Verify contest exists and user has permission
            contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
            if not contest:
                raise ContestNotFoundError(str(contest_id))
            
            # This will raise PermissionDeniedError if user doesn't have permission
            ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)
            
            team = self.db.query(Team).filter(Team.id == team_id).first()
            if not team:
                raise TeamNotFoundError(str(team_id))
            
            # Verify team belongs to this contest
            if team.contest_id != contest_id:
                raise TeamNotFoundError(str(team_id))
                
            response = TeamResponse.model_validate(team)
            
            # Delete all team members first (cascade would work but explicit is clearer)
            self.db.query(TeamUser).filter(TeamUser.team_id == team_id).delete()
            
            # Now delete the team
            self.db.delete(team)
            self.db.flush()
            logger.info(f"Team deleted successfully: {team.id}")
            return response
        
        except (ContestNotFoundError, TeamNotFoundError, PermissionDeniedError):
            self.db.rollback()
            raise
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting team: {str(e)}")
            raise AppBaseException("Failed to delete team", status_code=500)
    
    @cache_delete(
        key_builder=lambda self, team_id, user_id, contest_id, current_user_id: [
            f"team:{team_id}:members",
            f"teams:user:{user_id}:*",
        ]
    )
    async def add_member_to_team(self, team_id: UUID, user_id: UUID, contest_id: UUID, current_user_id: UUID) -> AddTeamMemberResponse:
        """
        Add a user to a team within a contest.

        Args:
            team_id: Team ID
            user_id: User ID to add to team
            contest_id: Contest ID (for validation)
            current_user_id: User ID performing the action (for permission check)

        Returns:
            Response object
            
        Raises:
            TeamNotFoundError: If team not found or doesn't belong to contest
            UserNotFoundError: If user not found
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user lacks permission to manage contest
            UserAlreadyInTeamError: If user already in team
        """
        try:
            # Verify contest exists and current user has permission
            contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
            if not contest:
                raise ContestNotFoundError(str(contest_id))
            
            # This will raise PermissionDeniedError if user doesn't have permission
            ContestPermission.can_manage_contest(self.db, user_id=current_user_id, contest=contest)
            
            # Verify team exists and belongs to contest
            team = await self.get_team_by_id(team_id, contest_id)

            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise UserNotFoundError(str(user_id))
            
            existing = self.db.query(TeamUser).filter(
                TeamUser.team_id == team_id,
                TeamUser.user_id == user_id
            ).first()

            if existing:
                raise UserAlreadyInTeamError(str(team_id), str(user_id))
            
            team_user = TeamUser(team_id=team_id, user_id=user_id)
            self.db.add(team_user)
            self.db.flush()
            self.db.refresh(team_user)
            logger.info(f"User {user_id} added to team {team_id}")
            return AddTeamMemberResponse(
                message="Member added successfully",
                user_id=user_id,
                team_id=team_id,
                added_at=datetime.now(timezone.utc)
            )
        
        except (ContestNotFoundError, TeamNotFoundError, UserNotFoundError, UserAlreadyInTeamError, PermissionDeniedError):
            self.db.rollback()
            raise
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error adding member to team: {str(e)}")
            raise AppBaseException("Failed to add member to team", status_code=500)
    
    @cache_delete(
        key_builder=lambda self, team_id, user_id, contest_id, current_user_id: [
            f"team:{team_id}:members",
            f"teams:user:{user_id}:*",
        ]
    )
    async def remove_member_from_team(self, team_id: UUID, user_id: UUID, contest_id: UUID, current_user_id: UUID) -> RemoveTeamMemberResponse:
        """
        Remove a user from a team within a contest.

        Args:
            team_id: Team ID
            user_id: User ID to remove from team
            contest_id: Contest ID (for validation)
            current_user_id: User ID performing the action (for permission check)

        Returns:
            Response object
            
        Raises:
            TeamNotFoundError: If team not found or doesn't belong to contest
            UserNotFoundError: If user not found
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user lacks permission to manage contest
            UserNotInTeamError: If user not in team
        """
        try:
            # Verify contest exists and current user has permission
            contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
            if not contest:
                raise ContestNotFoundError(str(contest_id))
            
            # This will raise PermissionDeniedError if user doesn't have permission
            ContestPermission.can_manage_contest(self.db, user_id=current_user_id, contest=contest)
            
            team = await self.get_team_by_id(team_id, contest_id)

            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise UserNotFoundError(str(user_id))
            
            team_user = self.db.query(TeamUser).filter(
                TeamUser.team_id == team_id,
                TeamUser.user_id == user_id
            ).first()

            if not team_user:
                raise UserNotInTeamError(str(team_id), str(user_id))
            
            self.db.delete(team_user)
            self.db.flush()
            logger.info(f"User {user_id} removed from the team {team_id}")
            return RemoveTeamMemberResponse(
                message="Member removed successfully",
                user_id=user_id,
                team_id=team_id,
                removed_at=datetime.now(timezone.utc)
            )
        
        except (ContestNotFoundError, TeamNotFoundError, UserNotFoundError, UserNotInTeamError, PermissionDeniedError):
            self.db.rollback()
            raise
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error removing member from team: {str(e)}")
            raise AppBaseException("Failed to remove member from team", status_code=500)

    @cache_get(
        key_builder=lambda self, team_id, contest_id: f"team:{team_id}:members:contest:{contest_id}",
        ttl=300,
    )
    async def get_team_members(self, team_id: UUID, contest_id: UUID) -> List[UserTeamResponse]:
        """
        Get all members of a team within a contest.

        Args:
            team_id: Team ID
            contest_id: Contest ID (for validation)

        Returns:
            List of User objects
            
        Raises:
            TeamNotFoundError: If team not found or doesn't belong to contest
        """
        team = await self.get_team_by_id(team_id, contest_id)

        team_users = (
            self.db.query(TeamUser)
            .options(joinedload(TeamUser.user))
            .filter(TeamUser.team_id == team_id)
            .all()
        )
        users = [tu.user for tu in team_users]
        return [UserTeamResponse.model_validate(user) for user in users]