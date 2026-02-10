from uuid import UUID

from keycloak import KeycloakAdmin
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.config import config
from app.core.logger import logger
from app.exceptions.user import KeycloakSyncError, UserNotFoundError
from app.models.user import User
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
                realm_name=config.KEYCLOAK_REALM,
                user_realm_name=config.KEYCLOAK_REALM,
                client_id=config.KEYCLOAK_USERS_SYNC_CLIENT_ID,
                client_secret_key=config.KEYCLOAK_USERS_SYNC_CLIENT_SECRET,
                verify=True,
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
                    logger.warning(f"Skipping user {name} (ID: {user_id}) - Missing email")
                    skipped_users.append({
                        "user_id": user_id,
                        "name": name,
                        "reason": "Missing email"
                    })
                    continue


                
                # Check if user already exists in database by ID or Email
                existing_user = db.query(User).filter(
                    or_(
                        User.user_id == user_id,
                        User.email == email
                    )
                ).first()

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
                    existing_user.user_id = user_id # Ensure ID matches Keycloak
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
                        role=user_role
                    )
                    db.add(new_user)
                
                users_synced += 1

            # Commit all changes to database
            if users_synced > 0:
                db.commit()

            return {
                "synced_count": users_synced,
                "skipped_count": len(skipped_users),
                "skipped_users": skipped_users
            }

        except KeycloakSyncError:
            db.rollback()
            logger.error("Failed to sync Keycloak users")
            raise
        except Exception as e:
            db.rollback()
            error_message = f"Failed to sync Keycloak users: {str(e)}"
            logger.error(error_message)
            raise KeycloakSyncError(error_message)
