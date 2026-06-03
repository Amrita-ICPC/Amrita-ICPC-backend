from datetime import datetime, timezone
from typing import AsyncGenerator, List, cast
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.core.clients.scheduler import scheduler
from app.core.guards.contest import ContestOperationGuard
from app.core.logger import logger
from app.core.permissions import AudiencePermission
from app.exceptions.contest import (
    AudienceNotAssignedToContestError,
    ContestNotFoundError,
    InvalidContestError,
)
from app.jobs.contest import ContestJobs
from app.mappers.contest import (
    apply_contest_updates,
    build_contest_entity,
    build_create_contest_dto,
    build_update_contest_dto,
    to_contest_response,
    to_contest_summary_response,
)
from app.models.contest import ContestRuntime
from app.repositories.audience import AudienceRepository
from app.repositories.contest import ContestRepository
from app.repositories.contest_runtime import ContestRuntimeRepository
from app.repositories.dto import (
    UNSET,
    ContestFilters,
    PaginationParams,
)
from app.repositories.team import TeamRepository
from app.repositories.user import UserRepository
from app.schema.contest import (
    ContestAudienceResponse,
    ContestCreate,
    ContestEvent,
    ContestResponse,
    ContestSummaryResponse,
    ContestUpdate,
    InstructorManageRequest,
    InstructorResponse,
)
from app.service.contest_event_publish import ContestEventPublisher
from app.utils.contest import compute_run_status
from app.utils.enums import (
    ContestRunStatus,
    ContestRuntimeStatus,
    ContestStatus,
    UserRole,
)
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
        audience_repository: AudienceRepository,
        team_repository: TeamRepository | None = None,
        runtime_repository: ContestRuntimeRepository | None = None,
        event_publisher: ContestEventPublisher | None = None,
    ):
        self.repository = repository
        self.user_repository = user_repository
        self.guard = guard
        self.validator = validator
        self.audience_repository = audience_repository
        self.team_repository = team_repository
        self.runtime_repository = runtime_repository or ContestRuntimeRepository(
            repository.db
        )
        self.event_publisher = event_publisher

    async def _validate_contest_not_deleted_and_has_permission(
        self, contest_id: UUID, user_id: UUID
    ) -> tuple[bool, object]:
        """
        Consolidated validation: Check if contest exists, not deleted, and user has manage permission.

        Eliminates repeated pattern across assign/remove audience methods.

        Args:
            contest_id: Contest ID to validate
            user_id: User performing operation

        Returns:
            Tuple of (can_manage, contest_object)

        Raises:
            ContestNotFoundError: If contest not found or deleted
            PermissionDeniedError: If user lacks permission
        """
        contest = await self.repository.get_contest_or_raise(contest_id)
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        user = await self.user_repository.get_user_or_raise(user_id)
        can_manage = user.role == UserRole.admin

        return can_manage, contest

    @cache_delete(
        key_builder=lambda self, contest, created_by: [
            "contests:*",
            "student:contests:user:*",
        ],
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

        # Validate audience membership for non-admins
        user = await self.user_repository.get_user_or_raise(created_by)
        is_admin = user.role == UserRole.admin

        if not is_admin and contest.audience_ids:
            await AudiencePermission.is_user_in_audience(
                self.repository.db,
                user_id=created_by,
                audience_ids=contest.audience_ids,
            )
        await self.audience_repository.get_audience_by_ids_or_raise(
            contest.audience_ids
        )
        contest_data = build_create_contest_dto(contest, created_by)
        contest_entity = build_contest_entity(contest_data)

        # Create contest via repository
        db_contest = await self.repository.create_contest(contest_entity)

        # Link audiences if provided
        if contest.audience_ids:
            await self.repository.link_audiences_to_contest(
                db_contest.id, contest.audience_ids
            )

        return to_contest_response(
            db_contest,
            run_status=compute_run_status(db_contest.start_time, db_contest.end_time),
        )

    @cache_get(
        key_builder=lambda self, contest_id, user_id: (
            f"contest:{contest_id}:user:{user_id}"
        ),
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

        team_count = 0
        participant_count = 0
        if self.team_repository is not None:
            team_count = await self.team_repository.count_teams_in_contest(contest_id)
            participant_count = (
                await self.team_repository.count_participants_in_contest(contest_id)
            )

        question_count = await self.repository.count_questions_in_contest(contest_id)
        submission_count = await self.repository.count_submissions_in_contest(
            contest_id
        )

        # Fetch runtime status — only exists for published contests
        runtime = await self.runtime_repository.get_contest_runtime_by_id(contest_id)
        contest_runtime_status = runtime.runtime_status if runtime is not None else None

        return to_contest_response(
            contest,
            run_status=compute_run_status(contest.start_time, contest.end_time),
            team_count=team_count,
            question_count=question_count,
            submission_count=submission_count,
            participant_count=participant_count,
            contest_runtime_status=contest_runtime_status,
        )

    @cache_get(
        key_builder=lambda self, user_id, search_term=None, status=None, run_status=None, is_public=None, skip=0, limit=100: (
            f"contests:user:{user_id}:search:{search_term}:status:{status}:run_status:{run_status}:public:{is_public}:skip:{skip}:limit:{limit}"
        ),
        ttl=300,
    )
    async def get_all_contests(
        self,
        user_id: UUID,
        search_term: str | None = None,
        status: ContestStatus | None = None,
        run_status: ContestRunStatus | None = None,
        is_public: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, List[ContestSummaryResponse]]:
        """
        Get all contests with pagination, search, and filtering.

        Args:
            user_id: User ID
            search_term: Optional search term for contest name
            status: Optional lifecycle status to filter by (DRAFT/PUBLISHED/etc)
            run_status: Optional temporal run-state to filter by (UPCOMING/LIVE/ENDED)
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
            search_term=search_term,
            status=status,
            run_status=run_status,
            is_public=is_public,
        )
        pagination = PaginationParams(skip=skip, limit=limit)

        # Get contests from repository (includes eager loaded audiences)
        result = await self.repository.get_contests_with_filters(
            user_id, user_is_admin, filters, pagination
        )

        return result.total, [
            to_contest_summary_response(
                contest,
                run_status=compute_run_status(contest.start_time, contest.end_time),
            )
            for contest in result.items
        ]

    @cache_delete(
        key_builder=lambda self, contest_id, audience_ids, user_id: [
            f"contest:{contest_id}*",
            "contests:*",
            "student:contests:user:*",
        ],
    )
    async def assign_audiences_to_contest(
        self, contest_id: UUID, audience_ids: list[UUID], user_id: UUID
    ) -> None:
        """
        Assign multiple audiences to a contest.

        Args:
            contest_id: ID of the contest
            audience_ids: List of audience IDs to assign
            user_id: ID of the user performing the operation

        Raises:
            ContestNotFoundError: If contest not found or is soft-deleted
            PermissionDeniedError: If user lacks permission to manage contest
            InvalidContestError: If any audience is already assigned to the contest
        """
        (
            can_manage,
            contest,
        ) = await self._validate_contest_not_deleted_and_has_permission(
            contest_id, user_id
        )

        # Validate audience membership for non-admins
        if not can_manage:
            await AudiencePermission.is_user_in_audience(
                self.repository.db, user_id=user_id, audience_ids=audience_ids
            )
        await self.audience_repository.get_audience_by_ids_or_raise(audience_ids)

        # Validate that audiences are NOT already assigned
        current_ids = await self.repository.get_contest_audience_ids(contest_id)
        for aid in audience_ids:
            if aid in current_ids:
                raise InvalidContestError(
                    f"Audience {aid} is already assigned to contest {contest_id}"
                )

        await self.repository.link_audiences_to_contest(contest_id, audience_ids)

    @cache_delete(
        key_builder=lambda self, contest_id, audience_ids, user_id: [
            "contests:*",
            "student:contests:user:*",
        ],
    )
    async def remove_audiences_from_contest(
        self, contest_id: UUID, audience_ids: list[UUID], user_id: UUID
    ) -> None:
        """
        Remove multiple audiences from a contest.

        Args:
            contest_id: ID of the contest
            audience_ids: List of audience IDs to remove
            user_id: ID of the user performing the operation

        Raises:
            AudienceNotAssignedToContestError: If any audience ID is not currently assigned
        """
        (
            can_manage,
            contest,
        ) = await self._validate_contest_not_deleted_and_has_permission(
            contest_id, user_id
        )

        # Validate audience membership for non-admins
        if not can_manage:
            await AudiencePermission.is_user_in_audience(
                self.repository.db, user_id=user_id, audience_ids=audience_ids
            )

        # Strict validation: Ensure all targeted IDs are currently assigned
        current_ids = await self.repository.get_contest_audience_ids(contest_id)
        for aid in audience_ids:
            if aid not in current_ids:
                raise AudienceNotAssignedToContestError(str(aid), str(contest_id))

        await self.repository.unlink_audiences_from_contest(contest_id, audience_ids)

    @cache_delete(
        key_builder=lambda self, contest_id, contest_data, user_id: [
            f"contest:{contest_id}*",
            "contests:*",
            "student:contests:user:*",
        ],
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

        update_data = build_update_contest_dto(contest_data)

        # Validate dates if being updated
        new_start = (
            update_data.start_time
            if update_data.start_time is not UNSET
            else contest.start_time
        )
        new_end = (
            update_data.end_time
            if update_data.end_time is not UNSET
            else contest.end_time
        )
        new_reg_start = (
            update_data.registration_start
            if update_data.registration_start is not UNSET
            else contest.registration_start
        )
        new_reg_end = (
            update_data.registration_end
            if update_data.registration_end is not UNSET
            else contest.registration_end
        )
        new_min_size = (
            update_data.min_team_size
            if update_data.min_team_size is not UNSET
            else contest.min_team_size
        )
        new_max_size = (
            update_data.max_team_size
            if update_data.max_team_size is not UNSET
            else contest.max_team_size
        )
        if new_start is None:
            raise InvalidContestError("start_time cannot be None")
        if new_min_size is None:
            raise InvalidContestError("min_team_size cannot be None")
        if new_max_size is None:
            raise InvalidContestError("max_team_size cannot be None")

        validated_start = cast(datetime, new_start)
        validated_end = cast(datetime | None, new_end)

        self.validator.validate_contest_dates(validated_start, validated_end)
        if new_reg_start is not None and new_reg_end is not None:
            self.validator.validate_registration_dates(
                cast(datetime, new_reg_start),
                cast(datetime, new_reg_end),
                validated_start,
            )
        self.validator.validate_team_size_constraints(
            cast(int, new_min_size), cast(int, new_max_size)
        )

        apply_contest_updates(contest, update_data)

        # Update contest via repository
        updated_contest = await self.repository.update_contest(contest, user_id)
        return to_contest_response(
            updated_contest,
            run_status=compute_run_status(
                updated_contest.start_time, updated_contest.end_time
            ),
        )

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}*",
            "contests:*",
            "student:contests:user:*",
        ],
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

        response = to_contest_response(
            contest,
            run_status=compute_run_status(contest.start_time, contest.end_time),
        )
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
        key_builder=lambda self, contest_id, user_id, skip=0, limit=100: (
            f"contest:{contest_id}:instructors:user:{user_id}:skip:{skip}:limit:{limit}"
        ),
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
            f"contest:{contest_id}*",
            "contests:*",
            "student:contests:user:*",
        ],
    )
    async def publish_contest(self, contest_id: UUID, user_id: UUID) -> None:
        """
        Publish a contest.

        Args:
            contest_id: Contest ID
            user_id: User ID publishing the contest

        Raises:
            ContestNotFoundError: If contest not found
            InvalidContestStateError: If contest is not in DRAFT status
            PermissionDeniedError: If user doesn't have permission
        """
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Check if contest is soft-deleted
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        # Validate contest state (must be DRAFT)
        self.validator.validate_contest_can_be_published(contest.status, contest_id)

        # Check permissions
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Publish contest
        await self.repository.publish_contest(contest, user_id)

        # Determine runtime status based on start_time
        now = datetime.now(timezone.utc)
        start_time = contest.start_time
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        if start_time > now:
            runtime_status = ContestRuntimeStatus.SCHEDULED
        else:
            runtime_status = ContestRuntimeStatus.RUNNING

        contest_runtime = ContestRuntime(
            contest_id=contest_id,
            runtime_status=runtime_status,
            end_time=contest.end_time,
        )
        await self.runtime_repository.create_contest_runtime(contest_runtime)

        # Schedule start job if in the future
        if start_time > now:
            scheduler.add_job(
                ContestJobs.auto_start_contest,
                trigger="date",
                run_date=start_time,
                args=[contest_id],
                id=f"start_contest_{contest_id}",
                replace_existing=True,
            )

        # Schedule finish job
        end_time = contest.end_time
        if end_time is not None:
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)

            scheduler.add_job(
                ContestJobs.finish_contest,
                trigger="date",
                run_date=end_time,
                args=[contest_id],
                id=f"finish_contest_{contest_id}",
                replace_existing=True,
            )

        logger.info(f"Contest {contest_id} published ")

    @cache_delete(
        key_builder=lambda self, contest_id, user_id: [
            f"contest:{contest_id}*",
            "contests:*",
            "student:contests:user:*",
        ],
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
            f"contest:{contest_id}*",
            "contests:*",
            "student:contests:user:*",
        ],
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
            InvalidContestStateError: If contest is not soft-deleted
            PermissionDeniedError: If user doesn't have permission
        """
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Validate contest is actually soft-deleted before restoring
        self.validator.validate_contest_can_be_restored(contest.is_deleted, contest_id)

        # Check permissions
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Restore contest
        restored_contest = await self.repository.restore_contest(contest)
        logger.info(f"Contest {contest_id} restored")
        return to_contest_response(
            restored_contest,
            run_status=compute_run_status(
                restored_contest.start_time, restored_contest.end_time
            ),
        )

    @cache_get(
        key_builder=lambda self, user_id, search_term=None, status=None, skip=0, limit=100: (
            f"contests:deleted:user:{user_id}:search:{search_term}:status:{status}:skip:{skip}:limit:{limit}"
        ),
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

    async def get_contest_audiences(
        self, contest_id: UUID, user_id: UUID
    ) -> list[ContestAudienceResponse]:
        """
        Retrieve all audiences associated with a contest.

        Args:
            contest_id: ID of the contest
            user_id: ID of the user requesting the audiences

        Returns:
            List of audiences with details
        """
        contest = await self.repository.get_contest_or_raise(contest_id)
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))
        await self.guard.check_read_contest(user_id=user_id, contest=contest)

        audiences = await self.repository.get_contest_audiences_with_details(contest_id)
        return [ContestAudienceResponse.model_validate(a) for a in audiences]

    async def pause_contest(self, contest_id: UUID, user_id: UUID) -> None:
        """
        Pause a running contest.

        Args:
            contest_id: ID of the contest
            user_id: ID of the user requesting the pause
        """
        contest = await self.repository.get_contest_or_raise(contest_id)
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        runtime = await self.runtime_repository.get_contest_runtime_or_raise(contest_id)
        self.validator.validate_contest_can_be_paused(runtime, contest_id)

        now = datetime.now(timezone.utc)
        runtime.runtime_status = ContestRuntimeStatus.PAUSED
        runtime.paused_at = now
        runtime.updated_by = user_id

        await self.runtime_repository.update_contest_runtime(runtime)

        if self.event_publisher:
            event = ContestEvent(
                type=ContestRuntimeStatus.PAUSED,
                payload={
                    "contest_id": str(contest_id),
                    "paused_at": now.isoformat(),
                },
            )
            await self.event_publisher.publish(contest_id, event)
            logger.info(f"Published event: {event.model_dump_json()}")
        if self.event_publisher is None:
            logger.warning("No event publisher")

    async def resume_contest(self, contest_id: UUID, user_id: UUID) -> None:
        """
        Resume a paused contest.

        Args:
            contest_id: ID of the contest
            user_id: ID of the user requesting the resume
        """
        contest = await self.repository.get_contest_or_raise(contest_id)
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        runtime = await self.runtime_repository.get_contest_runtime_or_raise(contest_id)
        self.validator.validate_contest_can_be_resumed(runtime, contest_id)

        now = datetime.now(timezone.utc)
        paused_at = runtime.paused_at
        if paused_at is not None:
            if paused_at.tzinfo is None:
                paused_at = paused_at.replace(tzinfo=timezone.utc)
            paused_duration = int((now - paused_at).total_seconds())
            runtime.total_paused_duration += max(paused_duration, 0)

        runtime.runtime_status = ContestRuntimeStatus.RUNNING
        runtime.paused_at = None
        runtime.updated_by = user_id

        await self.runtime_repository.update_contest_runtime(runtime)

        if self.event_publisher:
            event = ContestEvent(
                type=ContestRuntimeStatus.RUNNING,
                payload={
                    "contest_id": str(contest_id),
                    "resumed_at": now.isoformat(),
                    "total_paused_duration": runtime.total_paused_duration,
                },
            )

            await self.event_publisher.publish(contest_id, event)
            logger.info(f"Published event: {event.model_dump_json()}")

        if self.event_publisher is None:
            logger.warning("No event publisher")

    async def cancel_contest(self, contest_id: UUID, user_id: UUID) -> None:
        """
        Cancel a contest.

        Args:
            contest_id: ID of the contest
            user_id: ID of the user requesting the cancellation
        """
        contest = await self.repository.get_contest_or_raise(contest_id)
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        runtime = await self.runtime_repository.get_contest_runtime_or_raise(contest_id)
        self.validator.validate_contest_can_be_cancelled(runtime, contest_id)

        now = datetime.now(timezone.utc)
        runtime.runtime_status = ContestRuntimeStatus.CANCELLED
        runtime.cancelled_at = now
        runtime.updated_by = user_id

        await self.runtime_repository.update_contest_runtime(runtime)

        if self.event_publisher:
            event = ContestEvent(
                type=ContestRuntimeStatus.CANCELLED,
                payload={
                    "contest_id": str(contest_id),
                    "cancelled_at": now.isoformat(),
                },
            )
            await self.event_publisher.publish(contest_id, event)
            logger.info(f"Published event: {event.model_dump_json()}")

    async def subscribe_contest_events(
        self, contest_id: UUID
    ) -> AsyncGenerator[str, None]:
        """
        Subscribe to contest events and yield them as SSE data packets.

        Args:
            contest_id: ID of the contest

        Yields:
            str: SSE formatted data packet
        """
        if not self.event_publisher:
            raise RuntimeError("Event publisher is not initialized")
        async for msg in self.event_publisher.subscribe(contest_id):
            yield msg
