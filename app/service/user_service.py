from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import config
from app.core.logger import logger
from app.exceptions.user import UserNotFoundError, KeycloakSyncError
from app.models.user import User
from keycloak import KeycloakAdmin

from app.utils.enums import UserRole


class UserService:
    """Service for user database operations."""

    @staticmethod
    def get_user_by_keycloak_id(db: Session, keycloak_user_id: str) -> User:
        """
        Get a user from the database by their Keycloak user ID.

        Args:
            db: Database session
            keycloak_user_id: Keycloak user ID (from token 'sub' claim)

        Returns:
            User object

        Raises:
            UserNotFoundError: If user not found in database
        """
        user = db.query(User).filter(User.user_id == keycloak_user_id).first()
        if not user:
            raise UserNotFoundError(keycloak_user_id)
        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: UUID) -> User:
        """
        Get a user from the database by their database ID.

        Args:
            db: Database session
            user_id: Database user ID (UUID)

        Returns:
            User object

        Raises:
            UserNotFoundError: If user not found in database
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError(str(user_id))
        return user
    
    @staticmethod
    def sync_keycloak_users(db: Session) -> int:
        """
        Synchronize Keycloak users with the local database.

        This method fetches all users from Keycloak, retrieves their group assignments,
        and creates new user records in the database if they don't already exist.

        Args:
            db: Database session

        Returns:
            int: Number of users successfully synced to the database

        Raises:
            KeycloakSyncError: If sync operation fails
        """
        try:
            # Initialize Keycloak admin client
            keycloak_admin = KeycloakAdmin(
                server_url=config.KEYCLOAK_SERVER_URL,
                username=config.KEYCLOAK_ADMIN_USERNAME,
                password=config.KEYCLOAK_ADMIN_PASSWORD,
                realm_name="icpc",
                user_realm_name="master",
                client_id="admin-cli",
                client_secret_key=config.KEYCLOAK_CLIENT_SECRET,
            )

            # Fetch all users from Keycloak
            keycloak_users = keycloak_admin.get_users()
            users_synced = 0

            # Role mapping from Keycloak groups to application roles
            role_mapping = {
                "manager": UserRole.manager,
                "admin": UserRole.admin,
                "instructor": UserRole.instructor,
                "student": UserRole.student
            }

            # Process each Keycloak user
            for kc_user in keycloak_users:
                # Check if user already exists in database
                existing_user = db.query(User).filter(User.user_id == kc_user["id"]).first()
                if existing_user:
                    continue

                # Fetch user's groups from Keycloak
                user_id = kc_user["id"]
                user_groups = keycloak_admin.get_user_groups(user_id)

                # Determine user role from groups, default to student
                user_role = UserRole.student
                if user_groups:
                    group_name = user_groups[0]["name"]
                    user_role = role_mapping.get(group_name, UserRole.student)

                # Create new user record
                new_user = User(
                    user_id=user_id,
                    email=kc_user.get("email", ""),
                    name=f"{kc_user.get('firstName', '')} {kc_user.get('lastName', '')}".strip(),
                    phone_no=kc_user.get("attributes", {}).get("phone_no", [None])[0],
                    role=user_role
                )

                db.add(new_user)
                users_synced += 1

            # Commit all changes to database
            if users_synced > 0:
                db.commit()

            return users_synced

        except KeycloakSyncError:
            raise
        except Exception as e:
            error_message = f"Failed to sync Keycloak users: {str(e)}"
            logger.error(error_message)
            raise KeycloakSyncError(error_message)
