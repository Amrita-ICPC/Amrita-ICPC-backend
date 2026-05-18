from typing import Any, Dict
from uuid import UUID

from keycloak import KeycloakAdmin
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache.decorators import cache_delete, cache_get
from app.core.config import config
from app.core.logger import logger
from app.exceptions.user import KeycloakSyncError, UserNotFoundError
from app.models.audience import UserAudience
from app.models.user import User
from app.repositories.dto.user import UserListFilters
from app.repositories.user import UserRepository
from app.schema.user import UserResponse, StudentUserSearchResponse
from app.utils.enums import UserRole


class UserService:
    """Service for user database operations."""

    @staticmethod
    @cache_get(
        key_builder=lambda db, keycloak_user_id: f"user:keycloak:{keycloak_user_id}",
        ttl=300,
    )
    async def get_user_by_keycloak_id(
        db: AsyncSession, keycloak_user_id: str
    ) -> UserResponse:
        """
        Get a user from the database by their Keycloak user ID.

        Args:
            db: Database session
            keycloak_user_id: Keycloak user ID (from token 'sub' claim)

        Returns:
            User response model

        Raises:
            UserNotFoundError: If user not found in database
        """
        stmt = (
            select(User)
            .options(
                selectinload(User.audience_links).joinedload(UserAudience.audience)
            )
            .filter(User.user_id == keycloak_user_id)
        )
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user:
            raise UserNotFoundError(keycloak_user_id)
        return UserResponse.model_validate(user)

    @staticmethod
    @cache_get(
        key_builder=lambda db, user_id: f"user:id:{user_id}",
        ttl=300,
    )
    async def get_user_by_id(db: AsyncSession, user_id: UUID) -> UserResponse:
        """
        Get a user from the database by their database ID.

        Args:
            db: Database session
            user_id: Database user ID (UUID)

        Returns:
            User response model

        Raises:
            UserNotFoundError: If user not found in database
        """
        stmt = (
            select(User)
            .options(
                selectinload(User.audience_links).joinedload(UserAudience.audience)
            )
            .filter(User.id == user_id)
        )
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user:
            raise UserNotFoundError(str(user_id))
        return UserResponse.model_validate(user)

    @staticmethod
    @cache_get(
        key_builder=lambda db, filters, actor_id: (
            f"user:list:{actor_id}:{filters.role}:{filters.query}:{filters.audience_ids}:{filters.skip}:{filters.limit}"
        ),
        ttl=300,
    )
    async def list_users(
        db: AsyncSession, filters: UserListFilters, actor_id: UUID
    ) -> tuple[int, list[UserResponse]]:
        """List users with filtering and pagination.

        Args:
            db: Database session.
            filters: Filtering and pagination parameters.

        Returns:
            A tuple containing the total count and a list of user responses.
        """
        user_repo = UserRepository(db)
        result = await user_repo.list_users(filters)
        users = [UserResponse.model_validate(user) for user in result.items]
        return result.total, users

    @staticmethod
    @cache_delete(
        key_builder=lambda db: [
            "user:list:*",
        ]
    )
    async def sync_keycloak_users(db: AsyncSession) -> Dict[str, Any]:
        """
        Synchronize Keycloak users with the local database.

        This method fetches all users from Keycloak, retrieves their group assignments,
        and creates new user records in the database if they don't already exist.

        Args:
            db: Database session

        Returns:
            Dict[str, Any]: A dictionary containing:
                - "synced_count" (int): Number of users successfully synced
                - "skipped_count" (int): Number of users skipped
                - "skipped_users" (List[Dict]): List of skipped users with reasons

        Raises:
            KeycloakSyncError: If sync operation fails
        """
        try:
            # Initialize Keycloak admin client
            logger.info("KEYCLOAK REALM: %s", config.KEYCLOAK_REALM)
            logger.info("KEYCLOAK SERVER URL: %s", config.KEYCLOAK_SERVER_URL)
            logger.info(
                "KEYCLOAK USERS SYNC CLIENT ID: %s",
                config.KEYCLOAK_USERS_SYNC_CLIENT_ID,
            )
            logger.info(
                "KEYCLOAK USERS SYNC CLIENT SECRET: %s",
                config.KEYCLOAK_USERS_SYNC_CLIENT_SECRET,
            )

            keycloak_admin = KeycloakAdmin(
                server_url=config.KEYCLOAK_SERVER_URL,
                realm_name=config.KEYCLOAK_REALM,
                user_realm_name=config.KEYCLOAK_REALM,
                client_id=config.KEYCLOAK_USERS_SYNC_CLIENT_ID,
                client_secret_key=config.KEYCLOAK_USERS_SYNC_CLIENT_SECRET,
                verify=True,
            )
            logger.info("Starting Keycloak user synchronization")
            token = keycloak_admin.connection.token
            logger.info(
                "Successfully authenticated with Keycloak for user sync: %s", token
            )
            # Fetch all users from Keycloak
            keycloak_users = keycloak_admin.get_users()
            users_synced = 0
            skipped_users = []

            # Role mapping from Keycloak groups to application roles
            role_mapping = {
                "manager": UserRole.manager,
                "admin": UserRole.admin,
                "instructor": UserRole.instructor,
                "student": UserRole.student,
            }

            # Process each Keycloak user
            for kc_user in keycloak_users:
                user_id = kc_user["id"]
                email = kc_user.get("email", "")
                name = f"{kc_user.get('firstName', '')} {kc_user.get('lastName', '')}".strip()

                if not email:
                    logger.warning(
                        f"Skipping user {name} (ID: {user_id}) - Missing email"
                    )
                    skipped_users.append(
                        {"user_id": user_id, "name": name, "reason": "Missing email"}
                    )
                    continue

                # Check if user already exists in database by ID or Email
                result = await db.execute(
                    select(User).filter(
                        or_(User.user_id == user_id, User.email == email)
                    )
                )
                existing_user = result.scalars().first()

                # Fetch user's groups from Keycloak
                user_groups = keycloak_admin.get_user_groups(user_id)

                # Determine user role from groups, default to student
                user_role = UserRole.student
                if user_groups:
                    group_name = user_groups[0]["name"]
                    user_role = role_mapping.get(group_name, UserRole.student)

                phone_no = kc_user.get("attributes", {}).get("phone_no", [None])[0]

                if existing_user:
                    # Update existing user
                    existing_user.user_id = user_id  # Ensure ID matches Keycloak
                    existing_user.name = name
                    existing_user.email = email
                    existing_user.phone_no = phone_no
                    existing_user.role = user_role
                else:
                    # Create new user record
                    new_user = User(
                        user_id=user_id,
                        email=email,
                        name=name,
                        phone_no=phone_no,
                        role=user_role,
                    )
                    db.add(new_user)

                users_synced += 1

            # Commit all changes to database
            if users_synced > 0:
                await db.commit()

            return {
                "synced_count": users_synced,
                "skipped_count": len(skipped_users),
                "skipped_users": skipped_users,
            }

        except KeycloakSyncError:
            await db.rollback()
            logger.error("Failed to sync Keycloak users")
            raise
        except Exception as e:
            await db.rollback()
            error_message = f"Failed to sync Keycloak users: {str(e)}"
            logger.error(error_message)
            raise KeycloakSyncError(error_message)

    @staticmethod
    async def list_students_with_team_check(
        db: AsyncSession,
        filters: UserListFilters,
        actor_id: UUID,
        team_id: UUID | None = None,
    ) -> tuple[int, list[StudentUserSearchResponse]]:
        """List students with a check to see if they are already in the specified team.

        Args:
            db: Database session.
            filters: Filter options for the user search.
            actor_id: ID of the user executing the query.
            team_id: Optional team ID to check membership.

        Returns:
            A tuple of total count and the mapped list of StudentUserSearchResponse schemas.
        """
        total, users = await UserService.list_users(db, filters, actor_id=actor_id)

        # Check team membership and pending invitations if team_id is provided
        member_ids = set()
        invited_ids = set()
        if team_id:
            from app.models.team import TeamUser, TeamInvitation
            from app.utils.enums import TeamInvitationStatus

            stmt = select(TeamUser.user_id).where(TeamUser.team_id == team_id)
            res = await db.execute(stmt)
            member_ids = set(res.scalars().all())

            stmt_inv = select(TeamInvitation.reciever_id).where(
                TeamInvitation.team_id == team_id,
                TeamInvitation.status == TeamInvitationStatus.PENDING,
            )
            res_inv = await db.execute(stmt_inv)
            invited_ids = set(res_inv.scalars().all())

        # Map to StudentUserSearchResponse schemas
        mapped_users = []
        for user in users:
            is_in_team = user.id in member_ids if team_id else None
            is_already_invited = user.id in invited_ids if team_id else None
            mapped_users.append(
                StudentUserSearchResponse(
                    **user.model_dump(),
                    is_in_team=is_in_team,
                    is_already_invited=is_already_invited,
                )
            )

        return total, mapped_users

