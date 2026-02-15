from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.exceptions.contest import ContestNotFoundError, InstructorNotAssignedError
from app.models.contest import Contest, ContestInstructor
from app.models.user import User
from app.repositories.dto import (
    ContestFilters,
    CreateContestData,
    PaginatedResult,
    PaginationParams,
    UpdateContestData,
)
from app.utils.enums import ContestStatus


class ContestRepository:
    """Repository for contest-related database operations.

    This class implements the Repository Pattern, providing a clean abstraction
    over database operations for contest management. It encapsulates all SQL queries
    and ORM interactions, keeping the service layer database-agnostic.

    Responsibilities:
        - Execute all database queries for contests
        - Handle ORM relationships and eager loading optimizations
        - Provide type-safe data access methods
        - Raise domain-specific exceptions (not database exceptions)
        - Return domain objects and DTOs (not raw query results)

    Design Principles:
        - Single Responsibility: Only handles contest data access
        - Encapsulation: Hides SQLAlchemy implementation details
        - Fail Fast: Raises exceptions immediately on data not found
        - Type Safety: Uses DTOs for data transfer

    Key Methods:
        - Contest CRUD: create_contest, update_contest, delete_contest
        - Contest Queries: get_contest_or_raise, get_contests_with_filters
        - Soft Delete: soft_delete_contest, restore_contest, get_soft_deleted_contests
        - Publishing: publish_contest
        - Instructors: assign_instructor, remove_instructor, get_contest_instructors_paginated

    Exception Strategy:
        - Raises domain exceptions (ContestNotFoundError, etc.)
        - Never exposes SQLAlchemy exceptions to callers
        - Provides clear error messages with entity IDs
    """

    def __init__(self, db: Session):
        self.db = db

    def get_contest_or_raise(self, contest_id: UUID) -> Contest:
        """
        Retrieve a contest by its ID or raise an exception if not found.

        Args:
            contest_id: ID of the contest to retrieve.
        Returns:
            The Contest object if found.
        Raises:
            ContestNotFoundError: If the contest with the given ID does not exist.
        """
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(contest_id)
        return contest

    def get_contests_with_filters(
        self,
        user_id: UUID,
        is_admin: bool,
        filters: ContestFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve contests with optional filtering and pagination.

        This method builds a query based on user permissions (admin vs non-admin),
        applies filters for search, status, and visibility, and returns paginated results.

        Args:
            user_id: ID of the user requesting contests
            is_admin: Whether the user has admin privileges
            filters: ContestFilters object containing optional search_term, status, and is_public
            pagination: PaginationParams object containing skip and limit values

        Returns:
            PaginatedResult containing total count and list of Contest objects
        """
        base_query = self.db.query(Contest)

        # Non-admin users can only see contests they created or are assigned to as instructors
        if not is_admin:
            base_query = base_query.outerjoin(ContestInstructor).filter(
                or_(
                    Contest.created_by == user_id,
                    ContestInstructor.instructor_id == user_id,
                )
            )

        # Filter out soft-deleted contests
        base_query = base_query.filter(Contest.is_deleted.is_(False))

        # Apply search filter
        if filters.search_term:
            base_query = base_query.filter(
                Contest.name.ilike(f"%{filters.search_term}%")
            )

        # Apply status filter
        if filters.status:
            base_query = base_query.filter(Contest.status == filters.status)

        # Apply visibility filter
        if filters.is_public is not None:
            base_query = base_query.filter(Contest.is_public == filters.is_public)

        # Get distinct results (important when using outerjoin)
        base_query = base_query.distinct()

        # Get total count before pagination
        total = base_query.count()

        # Apply pagination
        contests = base_query.offset(pagination.skip).limit(pagination.limit).all()

        return PaginatedResult(total=total, items=contests)

    def get_soft_deleted_contests(
        self,
        user_id: UUID,
        is_admin: bool,
        filters: ContestFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve soft-deleted contests with optional filtering and pagination.

        Similar to get_contests_with_filters but only returns soft-deleted contests.

        Args:
            user_id: ID of the user requesting contests
            is_admin: Whether the user has admin privileges
            filters: ContestFilters object containing optional search_term and status
            pagination: PaginationParams object containing skip and limit values

        Returns:
            PaginatedResult containing total count and list of soft-deleted Contest objects
        """
        base_query = self.db.query(Contest)

        # Non-admin users can only see contests they created or are assigned to as instructors
        if not is_admin:
            base_query = base_query.outerjoin(ContestInstructor).filter(
                or_(
                    Contest.created_by == user_id,
                    ContestInstructor.instructor_id == user_id,
                )
            )

        # Filter for soft-deleted contests only
        base_query = base_query.filter(Contest.is_deleted.is_(True))

        # Apply search filter
        if filters.search_term:
            base_query = base_query.filter(
                Contest.name.ilike(f"%{filters.search_term}%")
            )

        # Apply status filter
        if filters.status:
            base_query = base_query.filter(Contest.status == filters.status)

        # Get distinct results
        base_query = base_query.distinct()

        # Get total count before pagination
        total = base_query.count()

        # Apply pagination
        contests = base_query.offset(pagination.skip).limit(pagination.limit).all()

        return PaginatedResult(total=total, items=contests)

    def create_contest(self, contest_data: CreateContestData) -> Contest:
        """
        Create a new contest in the database.

        Args:
            contest_data: CreateContestData object containing all contest creation data

        Returns:
            The created Contest object with ID and timestamps populated
        """
        db_contest = Contest(
            name=contest_data.name,
            description=contest_data.description,
            image=contest_data.image,
            is_public=contest_data.is_public,
            start_time=contest_data.start_time,
            end_time=contest_data.end_time,
            registration_start=contest_data.registration_start,
            registration_end=contest_data.registration_end,
            max_teams=contest_data.max_teams,
            min_team_size=contest_data.min_team_size,
            max_team_size=contest_data.max_team_size,
            rules=contest_data.rules,
            scoring_type=contest_data.scoring_type,
            created_by=contest_data.created_by,
        )
        self.db.add(db_contest)
        self.db.flush()
        self.db.refresh(db_contest)
        return db_contest

    def update_contest(
        self, contest: Contest, update_data: UpdateContestData, user_id: UUID
    ) -> Contest:
        """
        Update an existing contest in the database.

        Args:
            contest: Contest object to update (must have valid ID)
            update_data: UpdateContestData object with fields to update
            user_id: ID of the user performing the update

        Returns:
            The updated Contest object
        """
        # Apply updates for all non-None fields
        update_dict = update_data.__dict__
        for field, value in update_dict.items():
            if value is not None:
                setattr(contest, field, value)

        contest.updated_by = user_id
        self.db.flush()
        self.db.refresh(contest)
        return contest

    def delete_contest(self, contest: Contest) -> None:
        """
        Hard delete a contest from the database.

        Args:
            contest: Contest object to delete
        """
        self.db.delete(contest)
        self.db.flush()

    def soft_delete_contest(self, contest: Contest, user_id: UUID) -> None:
        """
        Soft delete a contest by setting deletion flags.

        Args:
            contest: Contest object to soft delete
            user_id: ID of the user performing the soft delete
        """
        contest.is_deleted = True
        contest.deleted_at = datetime.now(timezone.utc)
        contest.deleted_by = user_id
        self.db.flush()

    def restore_contest(self, contest: Contest) -> Contest:
        """
        Restore a soft-deleted contest.

        Args:
            contest: Contest object to restore

        Returns:
            The restored Contest object
        """
        contest.is_deleted = False
        contest.deleted_at = None
        contest.deleted_by = None
        self.db.flush()
        self.db.refresh(contest)
        return contest

    def publish_contest(self, contest: Contest, user_id: UUID) -> None:
        """
        Publish a contest by setting published timestamp and updating status.

        Args:
            contest: Contest object to publish
            user_id: ID of the user publishing the contest
        """
        now = datetime.now(timezone.utc)
        contest.published_at = now
        contest.published_by = user_id

        # Update status based on start/end times
        if now < contest.start_time:
            contest.status = ContestStatus.SCHEDULED
        elif contest.start_time <= now <= contest.end_time:
            contest.status = ContestStatus.RUNNING
        else:
            contest.status = ContestStatus.FINISHED

        self.db.flush()

    def get_all_instructors_for_contest(self, contest_id: UUID) -> list[User]:
        """
        Retrieve all instructors assigned to a contest.

        Args:
            contest_id: ID of the contest

        Returns:
            List of User objects representing the instructors assigned to the contest
        """
        instructors = (
            self.db.query(User)
            .join(ContestInstructor, User.id == ContestInstructor.instructor_id)
            .filter(ContestInstructor.contest_id == contest_id)
            .all()
        )
        return instructors

    def get_contest_instructors_paginated(
        self, contest_id: UUID, skip: int, limit: int
    ) -> tuple[int, list[User]]:
        """
        Retrieve instructors assigned to a contest with pagination.

        Args:
            contest_id: ID of the contest
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, list of User objects)
        """
        base_query = (
            self.db.query(User)
            .join(ContestInstructor, User.id == ContestInstructor.instructor_id)
            .filter(ContestInstructor.contest_id == contest_id)
        )

        total = base_query.count()
        instructors = base_query.offset(skip).limit(limit).all()

        return total, instructors

    def assign_instructor(self, contest_id: UUID, instructor_ids: list[UUID]) -> None:
        """
        Assign instructors to a contest.

        Args:
            contest_id: ID of the contest
            instructor_ids: List of instructor IDs to assign
        """
        existing_assignments = (
            self.db.query(ContestInstructor)
            .filter(
                ContestInstructor.contest_id == contest_id,
                ContestInstructor.instructor_id.in_(instructor_ids),
            )
            .all()
        )
        existing_instructor_ids = {
            assignment.instructor_id for assignment in existing_assignments
        }
        new_instructor_ids = [
            iid for iid in instructor_ids if iid not in existing_instructor_ids
        ]
        instructors = [
            ContestInstructor(contest_id=contest_id, instructor_id=instructor_id)
            for instructor_id in new_instructor_ids
        ]
        if instructors:
            self.db.add_all(instructors)
            self.db.flush()

    def remove_instructor(self, contest_id: UUID, instructor_ids: list[UUID]) -> None:
        """
        Remove instructors from a contest.

        Args:
            contest_id: ID of the contest
            instructor_ids: List of instructor IDs to remove
        """
        assignments = (
            self.db.query(ContestInstructor)
            .filter(
                ContestInstructor.contest_id == contest_id,
                ContestInstructor.instructor_id.in_(instructor_ids),
            )
            .all()
        )

        # Check if all instructors were found
        found_instructor_ids = {assignment.instructor_id for assignment in assignments}
        missing_instructor_ids = set(instructor_ids) - found_instructor_ids

        if missing_instructor_ids:
            # Raise exception for the first missing instructor ID
            missing_id = next(iter(missing_instructor_ids))
            raise InstructorNotAssignedError(str(missing_id), str(contest_id))

        # Delete all assignments
        for assignment in assignments:
            self.db.delete(assignment)

        self.db.flush()

    def is_instructor_assigned(self, contest_id: UUID, instructor_id: UUID) -> bool:
        """
        Check if an instructor is assigned to a contest.

        Args:
            contest_id: ID of the contest
            instructor_id: ID of the instructor

        Returns:
            True if the instructor is assigned, False otherwise
        """
        assignment = (
            self.db.query(ContestInstructor)
            .filter(
                ContestInstructor.contest_id == contest_id,
                ContestInstructor.instructor_id == instructor_id,
            )
            .first()
        )
        return assignment is not None

    def get_creator(self, user_id: UUID) -> User | None:
        """
        Get a user by ID for creator information.

        Args:
            user_id: ID of the user

        Returns:
            User object if found, None otherwise
        """
        return self.db.query(User).filter(User.id == user_id).first()
