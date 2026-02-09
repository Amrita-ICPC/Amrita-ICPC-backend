from uuid import UUID
from typing import List
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.core.logger import logger
from app.models.team import Team, TeamUser
from app.models.user import User
from app.schema.team import (
    TeamCreate, TeamUpdate, TeamResponse, 
    AddTeamMemberResponse, RemoveTeamMemberResponse, UserTeamResponse
)
from app.exceptions.team import (
    TeamNotFoundError, UserNotFoundError, 
    UserAlreadyInTeamError, UserNotInTeamError
)
from app.exceptions.base import AppBaseException
from app.core.cache.decorators import cache_delete, cache_get, cache_set


class TeamService:
    """Services for team database operation"""

    def __init__(self, db: Session):
        self.db = db

    @cache_delete(
        key_builder=lambda self, team_data: "teams:list:*",
    )
    @cache_set(
        key_builder=lambda team: f"team:{team.id}",
        ttl=300,
        from_result=True,
    )
    async def create_team(self, team_data: TeamCreate) -> TeamResponse:
        """
        Create a new team.

        Args:
            team_data: Team creation data

        Returns:
            Created Team object
        """
        try:
            team = Team(
                name=team_data.name,
                description=team_data.description,
                logo=team_data.logo
            )
            self.db.add(team)
            self.db.flush()
            self.db.refresh(team)
            logger.info(f"Team created successfully: {team.id}")
            return TeamResponse.model_validate(team)
        
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Integrity error creating team: {str(e)}")
            raise AppBaseException("Team with this name already exists", status_code=409)
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Unexpected error creating team: {str(e)}")
            raise AppBaseException("Failed to create team", status_code=500)

    @cache_get(
        key_builder=lambda self, team_id: f"team:{team_id}",
        ttl=300,
    )
    async def get_team_by_id(self, team_id: UUID) -> TeamResponse:
        """
        Get a team by its ID.

        Args:
            team_id: Team ID

        Returns:
            Team object
        """
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise TeamNotFoundError(str(team_id))
        return TeamResponse.model_validate(team)
    
    @cache_get(
        key_builder=lambda self, skip=0, limit=100: f"teams:list:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_all_teams(self, skip: int = 0, limit: int = 100) -> tuple[int, List[TeamResponse]]:
        """
        Get all teams with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, teams list)
        """
        base_query = self.db.query(Team)
        total = base_query.count()
        teams = base_query.offset(skip).limit(limit).all()
        return total, [TeamResponse.model_validate(team) for team in teams]
    
    @cache_get(
        key_builder=lambda self, user_id, skip=0, limit=100: f"teams:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_user_teams(self, user_id: UUID, skip: int = 0, limit: int = 100) -> tuple[int, List[TeamResponse]]:
        """
        Get all teams for a specific user with pagination.

        Args:
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, teams list)
        """
        base_query = (
            self.db.query(Team)
            .join(TeamUser)
            .filter(TeamUser.user_id == user_id)
            .distinct()
        )
        total = base_query.count()
        teams = base_query.offset(skip).limit(limit).all()
        return total, [TeamResponse.model_validate(team) for team in teams]
    
    @cache_delete(
        key_builder=lambda self, team_id, team_data: [
            "teams:list:*",
            "teams:user:*",
            f"team:{team_id}:members"
        ],
    )
    @cache_set(
        key_builder=lambda team: f"team:{team.id}",
        ttl=300,
        from_result=True,
    )
    async def update_team(self, team_id: UUID, team_data: TeamUpdate) -> TeamResponse:
        """
        Update a team.

        Args:
            team_id: Team ID
            team_data: Team update data

        Returns:
            Updated Team object
        """
        # Note: We must fetch from DB directly here to modify it
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if not team:
             raise TeamNotFoundError(str(team_id))

        update_data = team_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(team, field, value)
        
        try:
            self.db.flush()
            self.db.refresh(team)
            logger.info("Team updated successfully")
            return TeamResponse.model_validate(team)
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating team: {str(e)}")
            raise AppBaseException("Failed to update Team", status_code=500)

    @cache_delete(
        key_builder=lambda self, team_id: [
            f"team:{team_id}",
            f"team:{team_id}:members",
            "teams:list:*",
            "teams:user:*",
        ]
    )
    async def delete_team(self, team_id: UUID) -> TeamResponse:
        """
        Delete a team.

        Args:
            team_id: Team ID

        Returns:
            Deleted team object
        """
        team = self.db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise TeamNotFoundError(str(team_id))
            
        response = TeamResponse.model_validate(team)
        try:
            self.db.delete(team)
            self.db.flush()
            logger.info(f"Team deleted successfully: {team.id}")
            return response

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting team: {str(e)}")
            raise AppBaseException("Failed to delete team", status_code=500)
    
    @cache_delete(
        key_builder=lambda self, team_id, user_id: [
            f"team:{team_id}",
            f"team:{team_id}:members",
            f"teams:user:{user_id}:*",
        ]
    )
    async def add_member_to_team(self, team_id: UUID, user_id: UUID) -> AddTeamMemberResponse:
        """
        Add a user to a team.

        Args:
            team_id: Team ID
            user_id: User ID

        Returns:
            Response object
        """
        # Verify team exists (using the cached method is fine here)
        await self.get_team_by_id(team_id)

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError(str(user_id))
        
        existing = self.db.query(TeamUser).filter(
            TeamUser.team_id == team_id,
            TeamUser.user_id == user_id
        ).first()

        if existing:
            raise UserAlreadyInTeamError(str(team_id), str(user_id))
        
        try:
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
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error adding member to team: {str(e)}")
            raise AppBaseException("Failed to add member to team", status_code=500)
    
    @cache_delete(
        key_builder=lambda self, team_id, user_id: [
            f"team:{team_id}",
            f"team:{team_id}:members",
            f"teams:user:{user_id}:*",
        ]
    )
    async def remove_member_from_team(self, team_id: UUID, user_id: UUID) -> RemoveTeamMemberResponse:
        """
        Remove a user from a team.

        Args:
            team_id: Team ID
            user_id: User ID

        Returns:
            Response object
        """
        await self.get_team_by_id(team_id)

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError(str(user_id))
        
        team_user = self.db.query(TeamUser).filter(
            TeamUser.team_id == team_id,
            TeamUser.user_id == user_id
        ).first()

        if not team_user:
            raise UserNotInTeamError(str(team_id), str(user_id))
        
        try:
            self.db.delete(team_user)
            self.db.flush()
            logger.info(f"User {user_id} removed from the team {team_id}")
            return RemoveTeamMemberResponse(
                message="Member removed succesfully",
                user_id=user_id,
                team_id=team_id,
                removed_at=datetime.now(timezone.utc)
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error removing member from team: {str(e)}")
            raise AppBaseException("Failed to remove member from team", status_code=500)

    @cache_get(
        key_builder=lambda self, team_id: f"team:{team_id}:members",
        ttl=300,
    )
    async def get_team_members(self, team_id: UUID) -> List[UserTeamResponse]:
        """
        Get all members of a team.

        Args:
            team_id: Team ID

        Returns:
            List of User objects
        """
        await self.get_team_by_id(team_id)

        team_users = (
            self.db.query(TeamUser)
            .options(joinedload(TeamUser.user))
            .filter(TeamUser.team_id == team_id)
            .all()
        )
        users = [tu.user for tu in team_users]
        return [UserTeamResponse.model_validate(user) for user in users]