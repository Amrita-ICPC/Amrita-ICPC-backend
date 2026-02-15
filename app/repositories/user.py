from uuid import UUID

from sqlalchemy.orm import Session

from app.exceptions.user import UserNotFoundError
from app.models.user import User


class UserRepository:
    """Repository for user-related database operations.

    This class implements the Repository Pattern, providing a clean abstraction
    over database operations for user management. It encapsulates all SQL queries
    and ORM interactions related to users.

    Responsibilities:
        - Execute all database queries for users
        - Provide type-safe data access methods
        - Raise domain-specific exceptions (not database exceptions)
        - Return domain objects (not raw query results)

    Design Principles:
        - Single Responsibility: Only handles user data access
        - Encapsulation: Hides SQLAlchemy implementation details
        - Fail Fast: Raises exceptions immediately on data not found
        - Reusable: Can be used by any service requiring user data

    Key Methods:
        - get_user_or_raise: Retrieve single user by ID
        - get_users_or_raise: Retrieve multiple users by IDs
        - get_user_by_id: Retrieve user without raising exception

    Exception Strategy:
        - Raises UserNotFoundError when user(s) not found
        - Never exposes SQLAlchemy exceptions to callers
        - Provides clear error messages with user IDs
    """

    def __init__(self, db: Session):
        self.db = db

    def get_user_or_raise(self, user_id: UUID) -> User:
        """
        Retrieve a user by their ID or raise an exception if not found.

        Args:
            user_id: ID of the user to retrieve.
        Returns:
            The User object if found.
        Raises:
            UserNotFoundError: If the user with the given ID does not exist.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError(user_id)
        return user

    def get_users_or_raise(self, user_ids: list[UUID]) -> list[User]:
        """
        Retrieve multiple users by their IDs or raise an exception if any are not found.

        Args:
            user_ids: List of user IDs to retrieve.
        Returns:
            List of User objects corresponding to the provided IDs.
        Raises:
            UserNotFoundError: If any user with the given IDs does not exist.
        """
        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        if len(users) != len(user_ids):
            found_user_ids = {user.id for user in users}
            missing_user_ids = set(user_ids) - found_user_ids
            raise UserNotFoundError(str(next(iter(missing_user_ids))))
        return users

    def get_user_by_id(self, user_id: UUID) -> User | None:
        """
        Retrieve a user by their ID without raising an exception.

        Args:
            user_id: ID of the user to retrieve.
        Returns:
            The User object if found, otherwise None.
        """
        return self.db.query(User).filter(User.id == user_id).first()
