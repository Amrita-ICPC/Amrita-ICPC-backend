from uuid import UUID

from sqlalchemy.orm import Session

from app.exceptions.user import UserNotFoundError
from app.models.user import User


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
