from datetime import datetime, timezone
from typing import List
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.core.logger import logger
from app.core.permissions import ContestPermission, is_admin
from app.exceptions.contest import (
    ContestNotFoundError,
    InstructorAlreadyAssignedError,
    InstructorNotAssignedError,
    InvalidContestError,
)
from app.exceptions.user import UserNotFoundError
from app.models.contest import (
    Contest,
    ContestInstructor,
)
from app.models.user import User
from app.schema.contest import (
    ContestCreate,
    ContestResponse,
    ContestSummaryResponse,
    ContestUpdate,
    InstructorListResponse,
    InstructorManageRequest,
    InstructorResponse,
)
from app.utils.enums import ContestStatus


class ContestService:
    """Service for contest database operations."""

    def __init__(self, db: Session):
        self.db = db

    @cache_delete(
        key_builder=lambda self, contest, created_by: f"contests:user:{created_by}:*",
    )
    @cache_set(
        key_builder=lambda result: f"contest:{result.id}",
        ttl=300,
        from_result=True,
    )
    async def create_contest(
        self, contest: ContestCreate, created_by: UUID
    ) -> ContestResponse:
        """
        Create a new contest.

        Args:
            contest: Contest creation data
            created_by: User ID creating the contest

        Returns:
            Created contest object
        """
        db_contest = Contest(
            name=contest.name,
            description=contest.description,
            image=contest.image,
            is_public=contest.is_public,
            start_time=contest.start_time,
            end_time=contest.end_time,
            registration_start=contest.registration_start,
            registration_end=contest.registration_end,
            max_teams=contest.max_teams,
            min_team_size=contest.min_team_size,
            max_team_size=contest.max_team_size,
            rules=contest.rules,
            scoring_type=contest.scoring_type,
            created_by=created_by,
        )
        self.db.add(db_contest)
        self.db.flush()
        self.db.refresh(db_contest)
        return ContestResponse.model_validate(db_contest)

    @cache_get(
        key_builder=lambda self, contest_id, user_id: f"contest:{contest_id}",
        ttl=300,
    )
    async def get_contest_by_id(
        self, contest_id: UUID, user_id: UUID
    ) -> ContestResponse:
        """
        Get a contest by its ID.

        Args:
            contest_id: Contest ID
            user_id: User ID requesting the contest (for permission check)
        Returns:
            Contest object

        Raises:
            ContestNotFoundError: If contest not found
        """
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest or contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(
            self.db, user_id=user_id, contest=contest
        )  # Permission check for contest details

        return ContestResponse.model_validate(contest)

    @cache_get(
        key_builder=lambda self,
        user_id,
        skip=0,
        limit=100: f"contests:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_all_contests(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[int, List[ContestSummaryResponse]]:
        """
        Get all contests with pagination.

        Args:
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, contests list)
        """
        base_query = self.db.query(Contest)
        if not is_admin(self.db, user_id):
            base_query = base_query.outerjoin(ContestInstructor).filter(
                or_(
                    Contest.created_by == user_id,
                    ContestInstructor.instructor_id == user_id,
                )
            )

        base_query = base_query.filter(Contest.is_deleted.is_(False)).distinct()
        total = base_query.count()
        contests = base_query.offset(skip).limit(limit).all()
        return total, [
            ContestSummaryResponse.model_validate(contest) for contest in contests
        ]

    @cache_delete(
        key_builder=lambda self,
        contest_id,
        contest_data,
        user_id: f"contests:user:{user_id}:*",
    )
    @cache_set(
        key_builder=lambda result: f"contest:{result.id}",
        ttl=300,
        from_result=True,
    )
    async def update_contest(
        self, contest_id: UUID, contest_data: ContestUpdate, user_id: UUID
    ) -> ContestResponse:
        """
        Update an existing contest.

        Args:
            contest_id: Contest ID
            contest_data: Contest update data
            user_id: User ID performing update

        Returns:
            Updated contest object

        Raises:
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user doesn't have permission
            InvalidContestError: If update data is invalid
        """
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)

        update_data = contest_data.model_dump(exclude_unset=True)
        new_start = update_data.get("start_time", contest.start_time)
        new_end = update_data.get("end_time", contest.end_time)
        if new_end <= new_start:
            raise InvalidContestError("end_time must be after start_time")

        for field, value in update_data.items():
            setattr(contest, field, value)

        contest.updated_by = user_id
        self.db.flush()
        self.db.refresh(contest)
        return ContestResponse.model_validate(contest)

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}",
            f"contests:user:{user_id}:*",
        ]
    )
    async def delete_contest(self, contest_id: UUID, user_id: UUID) -> ContestResponse:
        """
        Delete a contest.

        Args:
            contest_id: Contest ID
            user_id: User ID performing delete

        Returns:
            Deleted contest object

        Raises:
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user doesn't have permission
        """
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)

        response = ContestResponse.model_validate(contest)
        self.db.delete(contest)
        self.db.flush()

        return response

    @cache_delete(
        key_builder=lambda self, contest_id, request, user_id: [
            f"contest:{contest_id}:instructors:*",
            f"contests:user:{user_id}:*",
            *[
                f"contests:user:{instructor_id}:*"
                for instructor_id in request.instructor_ids
            ],
        ]
    )
    async def assign_instructors_to_contest(
        self, contest_id: UUID, request: InstructorManageRequest, user_id: UUID
    ) -> None:
        """
        Assign instructors to a contest.

        Args:
            contest_id: Contest ID
            request: Request containing instructor IDs to assign
            user_id: User ID performing the assignment

        Raises:
            ContestNotFoundError: If contest not found
            UserNotFoundError: If any instructor not found
            InstructorAlreadyAssignedError: If any instructor is already assigned
            PermissionDeniedError: If user doesn't have permission
        """
        # Check if contest exists
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            logger.error(f"Contest {contest_id} not found")
            raise ContestNotFoundError(str(contest_id))

        # Check permissions
        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)

        # Validate instructors
        for instructor_id in request.instructor_ids:
            # Check if user exists
            instructor = self.db.query(User).filter(User.id == instructor_id).first()
            if not instructor:
                logger.error(f"Instructor {instructor_id} not found")
                raise UserNotFoundError(str(instructor_id))

            # Check if instructor is already assigned
            existing_assignment = (
                self.db.query(ContestInstructor)
                .filter(
                    ContestInstructor.contest_id == contest_id,
                    ContestInstructor.instructor_id == instructor_id,
                )
                .first()
            )
            if existing_assignment:
                logger.warning(
                    f"Instructor {instructor_id} is already assigned to contest {contest_id}"
                )
                raise InstructorAlreadyAssignedError(
                    str(instructor_id), str(contest_id)
                )

        # Assign instructors
        for instructor_id in request.instructor_ids:
            assignment = ContestInstructor(
                contest_id=contest_id, instructor_id=instructor_id
            )
            self.db.add(assignment)
            logger.info(
                f"Assigned instructor {instructor_id} to contest {contest_id} by user {user_id}"
            )

        self.db.flush()

    @cache_delete(
        key_builder=lambda self, contest_id, request, user_id: [
            f"contest:{contest_id}:instructors:*",
            f"contests:user:{user_id}:*",
            *[
                f"contests:user:{instructor_id}:*"
                for instructor_id in request.instructor_ids
            ],
        ]
    )
    async def remove_instructors_from_contest(
        self, contest_id: UUID, request: InstructorManageRequest, user_id: UUID
    ) -> None:
        """
        Remove instructors from a contest.

        Args:
            contest_id: Contest ID
            request: Request containing instructor IDs to remove
            user_id: User ID performing the removal

        Raises:
            ContestNotFoundError: If contest not found
            InstructorNotAssignedError: If any instructor is not assigned to the contest
            PermissionDeniedError: If user doesn't have permission
        """
        # Check if contest exists
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            logger.error(f"Contest {contest_id} not found")
            raise ContestNotFoundError(str(contest_id))

        # Check permissions
        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)

        # Validate assignments and remove
        for instructor_id in request.instructor_ids:
            assignment = (
                self.db.query(ContestInstructor)
                .filter(
                    ContestInstructor.contest_id == contest_id,
                    ContestInstructor.instructor_id == instructor_id,
                )
                .first()
            )
            if not assignment:
                logger.error(
                    f"Instructor {instructor_id} is not assigned to contest {contest_id}"
                )
                raise InstructorNotAssignedError(str(instructor_id), str(contest_id))

            self.db.delete(assignment)
            logger.info(
                f"Removed instructor {instructor_id} from contest {contest_id} by user {user_id}"
            )

        self.db.flush()

    @cache_get(
        key_builder=lambda self,
        contest_id,
        user_id,
        skip=0,
        limit=100: f"contest:{contest_id}:instructors:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_contest_instructors(
        self, contest_id: UUID, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> InstructorListResponse:
        """
        Get all instructors assigned to a contest.

        Args:
            contest_id: Contest ID
            user_id: User ID requesting the list (must have manage permissions)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of instructors assigned to the contest

        Raises:
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user cannot manage the contest
        """
        # Check if contest exists
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            logger.error(f"Contest {contest_id} not found")
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(
            self.db, user_id=user_id, contest=contest
        )  # Permission check for instructors list

        # Get instructors with pagination
        base_query = (
            self.db.query(User)
            .join(ContestInstructor, User.id == ContestInstructor.instructor_id)
            .filter(ContestInstructor.contest_id == contest_id)
        )

        total = base_query.count()
        instructors = base_query.offset(skip).limit(limit).all()

        instructor_responses = [
            InstructorResponse.model_validate(instructor) for instructor in instructors
        ]

        # Get creator information
        creator = None
        if contest.created_by:
            creator_user = (
                self.db.query(User).filter(User.id == contest.created_by).first()
            )
            if creator_user:
                creator = InstructorResponse.model_validate(creator_user)

        logger.info(
            f"Retrieved {len(instructor_responses)} instructors for contest {contest_id}"
        )

        return InstructorListResponse(
            total=total, instructors=instructor_responses, creator=creator
        )

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}",
            f"contests:user:{user_id}:*",
        ]
    )
    async def publish_contest(self, contest_id: UUID, user_id: UUID) -> None:
        """
        Publish a contest.

        Args:
            contest_id: Contest ID
            user_id: User ID publishing the contest

        Raises:
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user doesn't have permission
        """
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)

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
        logger.info(f"Contest {contest_id} published by user {user_id}")

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}",
            f"contests:user:{user_id}:*",
        ]
    )
    async def soft_delete_contest(self, contest_id: UUID, user_id: UUID) -> None:
        """
        Soft delete a contest.

        Args:
            contest_id: Contest ID
            user_id: User ID deleting the contest

        Raises:
            ContestNotFoundError: If contest not found
            PermissionDeniedError: If user doesn't have permission
        """
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest or contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)

        contest.is_deleted = True
        contest.deleted_at = datetime.now(timezone.utc)
        contest.deleted_by = user_id

        self.db.flush()
        logger.info(f"Contest {contest_id} soft deleted by user {user_id}")

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}",
            f"contests:user:{user_id}:*",
        ]
    )
    async def restore_contest(self, contest_id: UUID, user_id: UUID) -> ContestResponse:
        """
        Restore a soft-deleted contest.

        Args:
            contest_id: Contest ID
            user_id: User ID restoring the contest

        Returns:
            Restored contest object

        Raises:
            ContestNotFoundError: If contest not found (even if deleted)
            PermissionDeniedError: If user doesn't have permission
        """
        contest = self.db.query(Contest).filter(Contest.id == contest_id).first()
        # Find the contest, even if it is soft deleted.
        if not contest:
            raise ContestNotFoundError(str(contest_id))

        ContestPermission.can_manage_contest(self.db, user_id=user_id, contest=contest)

        if contest.is_deleted:
            contest.is_deleted = False
            contest.deleted_at = None
            contest.deleted_by = None
            self.db.flush()
            self.db.refresh(contest)
            logger.info(f"Contest {contest_id} restored by user {user_id}")

        return ContestResponse.model_validate(contest)

    @cache_get(
        key_builder=lambda self,
        user_id,
        skip=0,
        limit=100: f"contests:deleted:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_soft_deleted_contests(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[int, List[ContestSummaryResponse]]:
        """
        Get all soft-deleted contests with pagination.

        Args:
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, contests list)
        """
        base_query = self.db.query(Contest)
        if not is_admin(self.db, user_id):
            base_query = base_query.outerjoin(ContestInstructor).filter(
                or_(
                    Contest.created_by == user_id,
                    ContestInstructor.instructor_id == user_id,
                )
            )

        base_query = base_query.filter(Contest.is_deleted.is_(True)).distinct()
        total = base_query.count()
        contests = base_query.offset(skip).limit(limit).all()
        return total, [
            ContestSummaryResponse.model_validate(contest) for contest in contests
        ]
