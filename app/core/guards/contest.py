from uuid import UUID

from sqlalchemy.orm import Session

from app.core.permissions import ContestPermission
from app.models.contest import Contest


class ContestOperationGuard:
    """Guard for contest operation permission validation.

    This class implements the Guard Pattern, centralizing all permission checks
    for contest-related operations. It ensures users have appropriate permissions
    before allowing operations to proceed.

    Responsibilities:
        - Validate contest management permissions
        - Validate contest read permissions
        - Validate instructor assignment/removal permissions
        - Enforce role-based access control

    Design Principles:
        - Single Responsibility: Only handles permission validation
        - Fail Fast: Raises PermissionDeniedError immediately on failure
        - Centralized Logic: All permission checks in one place
        - Reusable: Called by service layer before operations

    Guard Methods:
        - check_manage_contest: Validates contest management permissions
        - check_read_contest: Validates contest read permissions
        - check_assign_instructors: Validates instructor assignment permissions
        - check_remove_instructors: Validates instructor removal permissions

    Exception Strategy:
        - Raises PermissionDeniedError when user lacks permission
        - Provides clear error messages for debugging
    """

    def __init__(self, db: Session):
        self.db = db

    def check_manage_contest(self, user_id: UUID, contest: Contest) -> None:
        """
        Validates that the user has permission to manage the contest.

        This includes permissions to update, delete, publish, and manage instructors.

        Args:
            user_id: ID of the user attempting the operation
            contest: Contest object being managed

        Raises:
            PermissionDeniedError: If user lacks management permission
        """
        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)

    def check_read_contest(self, user_id: UUID, contest: Contest) -> None:
        """
        Validates that the user has permission to read the contest.

        Args:
            user_id: ID of the user attempting to read
            contest: Contest object being read

        Raises:
            PermissionDeniedError: If user lacks read permission
        """
        ContestPermission.can_read_contest(self.db, user_id=user_id, contest=contest)

    def check_assign_instructors(
        self, user_id: UUID, contest: Contest, instructor_ids: list[UUID]
    ) -> None:
        """
        Validates that the user has permission to assign instructors to the contest.

        Args:
            user_id: ID of the user attempting to assign instructors
            contest: Contest object to assign instructors to
            instructor_ids: List of instructor IDs to assign

        Raises:
            PermissionDeniedError: If user lacks management permission
        """
        # Assigning instructors requires contest management permission
        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)

    def check_remove_instructors(
        self, user_id: UUID, contest: Contest, instructor_ids: list[UUID]
    ) -> None:
        """
        Validates that the user has permission to remove instructors from the contest.

        Args:
            user_id: ID of the user attempting to remove instructors
            contest: Contest object to remove instructors from
            instructor_ids: List of instructor IDs to remove

        Raises:
            PermissionDeniedError: If user lacks management permission
        """
        # Removing instructors requires contest management permission
        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)
