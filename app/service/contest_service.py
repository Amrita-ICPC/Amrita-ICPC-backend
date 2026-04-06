from typing import List
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.core.guards.contest import ContestOperationGuard
from app.core.logger import logger
from app.exceptions.contest import ContestNotFoundError, InvalidContestError
from app.mappers.contest import (
    apply_contest_updates,
    build_contest_entity,
    build_create_contest_dto,
    build_update_contest_dto,
    to_contest_response,
    to_contest_summary_response,
)
from app.repositories.contest import ContestRepository
from app.repositories.dto import (
    ContestFilters,
    PaginationParams,
)
from app.repositories.user import UserRepository
from app.schema.contest import (
    ContestCreate,
    ContestResponse,
    ContestSummaryResponse,
    ContestUpdate,
    InstructorManageRequest,
    InstructorResponse,
)
from app.utils.enums import ContestStatus, UserRole
from app.validators.contest import ContestValidator


class ContestService:
    """Service layer for contest management operations.

    This service orchestrates contest-related business logic by coordinating between
    the repository layer (data access), guard layer (permissions), and validator
    layer (business rules). It implements a clean architecture pattern with clear
    separation of concerns.

    Architecture:
        - Repository Pattern: All database operations delegated to ContestRepository
        - Guard Pattern: Permission checks centralized in ContestOperationGuard
        - Validator Pattern: Business rule validation in ContestValidator
        - No direct database access: Service layer remains database-agnostic

    Key Responsibilities:
        - Orchestrate contest CRUD operations (create, read, update, delete)
        - Manage contest lifecycle (publish, soft delete, restore)
        - Manage contest instructors (assign, remove, list)
        - Enforce permission checks before operations
        - Validate business rules (dates, team sizes, etc.)
        - Transform repository data to API response schemas
        - Coordinate cache invalidation for contest-related data

    Dependencies:
        - ContestRepository: Handles all database queries and mutations
        - UserRepository: Handles user-related database queries
        - ContestOperationGuard: Validates user permissions for operations
        - ContestValidator: Enforces business rules and constraints

    Cache Strategy:
        - Contest data cached with TTL of 300 seconds
        - Cache keys include user_id for permission-aware caching
        - Cache invalidated on contest mutations (create, update, delete)
    """

    def __init__(
        self,
        repository: ContestRepository,
        user_repository: UserRepository,
        guard: ContestOperationGuard,
        validator: ContestValidator,
    ):
        self.repository = repository
        self.user_repository = user_repository
        self.guard = guard
        self.validator = validator

    @cache_delete(
        key_builder=lambda self, contest, created_by: "contests:*",
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

        Raises:
            InvalidContestError: If contest data is invalid
        """
        # Validate contest data
        self.validator.validate_contest_dates(contest.start_time, contest.end_time)
        self.validator.validate_registration_dates(
            contest.registration_start, contest.registration_end, contest.start_time
        )
        self.validator.validate_team_size_constraints(
            contest.min_team_size, contest.max_team_size
        )

        contest_data = build_create_contest_dto(contest, created_by)
        contest_entity = build_contest_entity(contest_data)

        # Create contest via repository
        db_contest = await self.repository.create_contest(contest_entity)
        return to_contest_response(db_contest)

    @cache_get(
        key_builder=lambda self,
        contest_id,
        user_id: f"contest:{contest_id}:user:{user_id}",
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
            PermissionDeniedError: If user lacks read permission
        """
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Check if contest is soft-deleted
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        # Check permissions
        await self.guard.check_read_contest(user_id=user_id, contest=contest)

        return to_contest_response(contest)

    @cache_get(
        key_builder=lambda self,
        user_id,
        search_term=None,
        status=None,
        is_public=None,
        skip=0,
        limit=100: f"contests:user:{user_id}:search:{search_term}:status:{status}:public:{is_public}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_all_contests(
        self,
        user_id: UUID,
        search_term: str | None = None,
        status: ContestStatus | None = None,
        is_public: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, List[ContestSummaryResponse]]:
        """
        Get all contests with pagination, search, and filtering.

        Args:
            user_id: User ID
            search_term: Optional search term for contest name
            status: Optional status to filter by
            is_public: Optional visibility filter
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, contests list)
        """
        # Check if user is admin
        user = await self.user_repository.get_user_or_raise(user_id)
        user_is_admin = user.role == UserRole.admin
        # Create filter and pagination objects
        filters = ContestFilters(
            search_term=search_term, status=status, is_public=is_public
        )
        pagination = PaginationParams(skip=skip, limit=limit)

        # Get contests from repository
        result = await self.repository.get_contests_with_filters(
            user_id, user_is_admin, filters, pagination
        )

        return result.total, [
            to_contest_summary_response(contest) for contest in result.items
        ]

    @cache_delete(
        key_builder=lambda self, contest_id, contest_data, user_id: "contests:*",
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
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Check permissions
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Validate dates if being updated
        new_start = (
            contest_data.start_time
            if contest_data.start_time is not None
            else contest.start_time
        )
        new_end = (
            contest_data.end_time
            if contest_data.end_time is not None
            else contest.end_time
        )
        new_reg_start = (
            contest_data.registration_start
            if contest_data.registration_start is not None
            else contest.registration_start
        )
        new_reg_end = (
            contest_data.registration_end
            if contest_data.registration_end is not None
            else contest.registration_end
        )
        new_min_size = (
            contest_data.min_team_size
            if contest_data.min_team_size is not None
            else contest.min_team_size
        )
        new_max_size = (
            contest_data.max_team_size
            if contest_data.max_team_size is not None
            else contest.max_team_size
        )
        if new_start is None:
            raise InvalidContestError("start_time cannot be None")
        if new_end is None:
            raise InvalidContestError("end_time cannot be None")
        if new_reg_start is None or new_reg_end is None:
            raise InvalidContestError("registration dates required")

        self.validator.validate_contest_dates(new_start, new_end)
        self.validator.validate_registration_dates(
            new_reg_start, new_reg_end, new_start
        )
        self.validator.validate_team_size_constraints(new_min_size, new_max_size)

        update_data = build_update_contest_dto(contest_data)
        apply_contest_updates(contest, update_data)

        # Update contest via repository
        updated_contest = await self.repository.update_contest(contest, user_id)
        return to_contest_response(updated_contest)

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}",
            "contests:*",
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
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Check permissions
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        response = to_contest_response(contest)
        await self.repository.delete_contest(contest)

        return response

    @cache_delete(
        key_builder=lambda self, contest_id, request, user_id: [
            f"contest:{contest_id}:instructors:*",
            "contests:*",
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
        # Check if contest exists and user has permission
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_assign_instructors(
            user_id=user_id, contest=contest, instructor_ids=request.instructor_ids
        )

        await self.user_repository.get_users_or_raise(request.instructor_ids)
        # Validate instructors and assign
        existing_instructors = await self.repository.get_all_instructors_for_contest(
            contest_id
        )
        existing_instructor_ids = [instructor.id for instructor in existing_instructors]

        self.validator.validate_instructors_not_in_contest(
            existing_instructor_ids, request.instructor_ids
        )

        # Assign instructors
        await self.repository.assign_instructor(contest_id, request.instructor_ids)
        logger.info(
            f"Assigned {len(request.instructor_ids)} instructor(s) to contest {contest_id} "
        )

    @cache_delete(
        key_builder=lambda self, contest_id, request, user_id: [
            f"contest:{contest_id}:instructors:*",
            "contests:*",
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
        # Check if contest exists and user has permission
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_remove_instructors(
            user_id=user_id, contest=contest, instructor_ids=request.instructor_ids
        )

        await self.user_repository.get_users_or_raise(
            request.instructor_ids
        )  # Validate instructor IDs

        # Validate assignments and remove
        instructors = await self.repository.get_all_instructors_for_contest(contest_id)
        existing_instructor_ids = {instructor.id for instructor in instructors}

        self.validator.validate_instructors_in_contest(
            set(request.instructor_ids), existing_instructor_ids
        )
        # Remove instructors
        await self.repository.remove_instructor(contest_id, request.instructor_ids)
        logger.info(
            f"Removed {len(request.instructor_ids)} instructor(s) from contest {contest_id} "
        )

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
    ) -> tuple[int, list[InstructorResponse]]:
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
        # Check if contest exists and user has permission
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Get instructors with pagination
        total, instructors = await self.repository.get_contest_instructors_paginated(
            contest_id, skip, limit
        )

        instructor_responses = [
            InstructorResponse.model_validate(instructor) for instructor in instructors
        ]

        logger.info(
            f"Retrieved {len(instructor_responses)} instructors for contest {contest_id}"
        )

        return total, instructor_responses

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}",
            "contests:*",
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
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Check if contest is soft-deleted
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        # Check permissions
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Publish contest
        await self.repository.publish_contest(contest, user_id)
        logger.info(f"Contest {contest_id} published ")

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}",
            "contests:*",
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
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Check if already soft-deleted
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        # Check permissions
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Soft delete contest
        await self.repository.soft_delete_contest(contest, user_id)
        logger.info(f"Contest {contest_id} soft deleted")

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}",
            "contests:*",
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
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Check permissions
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Restore contest if it was soft-deleted
        if contest.is_deleted:
            restored_contest = await self.repository.restore_contest(contest)
            logger.info(f"Contest {contest_id} restored")
            return ContestResponse.model_validate(restored_contest)

        return ContestResponse.model_validate(contest)

    @cache_get(
        key_builder=lambda self,
        user_id,
        search_term=None,
        status=None,
        skip=0,
        limit=100: f"contests:deleted:user:{user_id}:search:{search_term}:status:{status}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_soft_deleted_contests(
        self,
        user_id: UUID,
        search_term: str | None = None,
        status: ContestStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, List[ContestSummaryResponse]]:
        """
        Get all soft-deleted contests with pagination, search, and filtering.

        Args:
            user_id: User ID
            search_term: Optional search term for contest name
            status: Optional status to filter by
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, contests list)
        """
        # Check if user is admin
        user = await self.user_repository.get_user_or_raise(user_id)
        user_is_admin = user.role == UserRole.admin

        # Create filter and pagination objects
        filters = ContestFilters(search_term=search_term, status=status)
        pagination = PaginationParams(skip=skip, limit=limit)

        # Get soft-deleted contests from repository
        result = await self.repository.get_soft_deleted_contests(
            user_id, user_is_admin, filters, pagination
        )

        return result.total, [
            ContestSummaryResponse.model_validate(contest) for contest in result.items
        ]
