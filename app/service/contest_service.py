from datetime import datetime
from typing import List, cast
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.core.guards.contest import ContestOperationGuard
from app.core.logger import logger
from app.core.permissions import AudiencePermission
from app.exceptions.contest import (
    AudienceNotAssignedToContestError,
    ContestNotFoundError,
    DuplicateQuestionOrderError,
    InvalidContestError,
    QuestionAlreadyInContestError,
    QuestionNotInContestError,
)
from app.exceptions.question import InvalidQuestionError, TemplateAlreadyExistsError
from app.mappers.contest import (
    apply_contest_updates,
    build_contest_entity,
    build_create_contest_dto,
    build_update_contest_dto,
    to_contest_response,
    to_contest_summary_response,
)
from app.mappers.contest_question import (
    build_add_contest_question_dto,
    to_contest_question_response,
)
from app.mappers.question import (
    apply_question_updates,
    build_appended_testcase_dtos,
    build_create_testcase_dtos,
    build_metadata_update_dto,
    build_testcase_entities,
)
from app.models.question import Question, QuestionTemplate
from app.repositories.audience import AudienceRepository
from app.repositories.contest import ContestRepository
from app.repositories.dto import (
    ContestFilters,
    PaginationParams,
)
from app.repositories.dto.contest import UNSET, ContestQuestionFilters
from app.repositories.dto.question import UpdateQuestionData
from app.repositories.question import QuestionRepository
from app.repositories.team import TeamRepository
from app.repositories.user import UserRepository
from app.schema.contest import (
    AddContestQuestionsRequest,
    ContestAudienceResponse,
    ContestCreate,
    ContestQuestionResponse,
    ContestResponse,
    ContestSummaryResponse,
    ContestUpdate,
    InstructorManageRequest,
    InstructorResponse,
    RemoveContestQuestionRequest,
)
from app.schema.question import (
    AddQuestionAllowedLanguagesRequest,
    AddQuestionTemplatesRequest,
    AddQuestionTestCasesRequest,
    QuestionListSummaryResponse,
    QuestionResponse,
    RemoveQuestionAllowedLanguagesRequest,
    RemoveQuestionTemplatesRequest,
    RemoveQuestionTestCasesRequest,
    UpdateQuestionAllowedLanguagesRequest,
    UpdateQuestionMetadataRequest,
    UpdateQuestionTemplateRequest,
    UpdateQuestionTestCaseRequest,
)
from app.utils.contest import compute_run_status
from app.utils.enums import (
    ContestRunStatus,
    ContestStatus,
    QuestionDifficulty,
    UserRole,
)
from app.validators.contest import ContestValidator
from app.validators.question import QuestionValidator


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
        question_repository: QuestionRepository | None = None,
        team_repository: TeamRepository | None = None,
    ):
        self.repository = repository
        self.user_repository = user_repository
        self.guard = guard
        self.validator = validator
        self.audience_repository = audience_repository
        self.question_repository = question_repository
        self.team_repository = team_repository

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

        return to_contest_response(
            contest,
            run_status=compute_run_status(contest.start_time, contest.end_time),
            team_count=team_count,
            question_count=question_count,
            submission_count=submission_count,
            participant_count=participant_count,
        )

    @cache_get(
        key_builder=lambda self,
        contest_id,
        user_id,
        search_term=None,
        difficulty=None,
        language_id=None,
        tag_id=None,
        skip=0,
        limit=100: f"contest:{contest_id}:questions:user:{user_id}:search:{search_term}:difficulty:{difficulty}:language:{language_id}:tag:{tag_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_contest_questions(
        self,
        contest_id: UUID,
        user_id: UUID,
        search_term: str | None = None,
        difficulty: QuestionDifficulty | None = None,
        language_id: int | None = None,
        tag_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[QuestionListSummaryResponse]]:
        """Get paginated contest questions as overview summaries."""
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_read_contest(user_id=user_id, contest=contest)

        pagination = PaginationParams(skip=skip, limit=limit)
        filters = ContestQuestionFilters(
            search_term=search_term,
            difficulty=difficulty,
            language_id=language_id,
            tag_id=tag_id,
        )
        result = await self.repository.get_contest_questions_paginated(
            contest_id, pagination, filters
        )
        return result.total, [
            QuestionListSummaryResponse.from_question(question)
            for question in result.items
        ]

    @cache_get(
        key_builder=lambda self,
        contest_id,
        question_id,
        user_id: f"contest:{contest_id}:questions:item:{question_id}:user:{user_id}",
        ttl=300,
    )
    async def get_contest_question(
        self, contest_id: UUID, question_id: UUID, user_id: UUID
    ) -> QuestionResponse:
        """Get a contest question by ID."""
        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )
        return QuestionResponse.from_question(question)

    @cache_get(
        key_builder=lambda self,
        user_id,
        search_term=None,
        status=None,
        run_status=None,
        is_public=None,
        skip=0,
        limit=100: f"contests:user:{user_id}:search:{search_term}:status:{status}:run_status:{run_status}:public:{is_public}:skip:{skip}:limit:{limit}",
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
        key_builder=lambda self, contest_id, audience_ids, user_id: "contests:*",
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
        """
        contest = await self.repository.get_contest_or_raise(contest_id)
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Validate audience membership for non-admins
        user = await self.user_repository.get_user_or_raise(user_id)
        if user.role != UserRole.admin:
            await AudiencePermission.is_user_in_audience(
                self.repository.db, user_id=user_id, audience_ids=audience_ids
            )
        await self.audience_repository.get_audience_by_ids_or_raise(audience_ids)

        await self.repository.link_audiences_to_contest(contest_id, audience_ids)

    @cache_delete(
        key_builder=lambda self, contest_id, audience_ids, user_id: "contests:*",
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
        contest = await self.repository.get_contest_or_raise(contest_id)
        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Validate audience membership for non-admins
        user = await self.user_repository.get_user_or_raise(user_id)
        if user.role != UserRole.admin:
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
        if new_end is None:
            raise InvalidContestError("end_time cannot be None")
        if new_min_size is None:
            raise InvalidContestError("min_team_size cannot be None")
        if new_max_size is None:
            raise InvalidContestError("max_team_size cannot be None")

        validated_start = cast(datetime, new_start)
        validated_end = cast(datetime, new_end)

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

    @cache_delete(
        key_builder=lambda self, contest_id, request, user_id: [
            f"contest:{contest_id}:questions:*",
        ]
    )
    async def add_questions_to_contest(
        self,
        contest_id: UUID,
        request: AddContestQuestionsRequest,
        user_id: UUID,
    ) -> list[ContestQuestionResponse]:
        """
        Add multiple questions to a contest in batch.

        This method orchestrates batch addition of questions by performing the same
        validation steps for each question (permission, existence, duplication checks)
        and then inserting all valid questions in a single batch operation.

        Permission Check:
            Only users who can manage the contest can add questions.

        Validation Workflow (for each question):
            1. Contest existence check (performed once)
            2. Question existence check
            3. Question not already in contest check
            4. Order, duration, and score validation

        Args:
            contest_id: UUID of the contest to add questions to.
            request: AddContestQuestionsRequest containing list of questions.
            user_id: UUID of the authenticated user performing the operation.

        Returns:
            list[ContestQuestionResponse]: List of newly created contest-question relationships.

        Raises:
            ContestNotFoundError: If contest does not exist.
            QuestionNotFoundError: If any question does not exist.
            QuestionAlreadyInContestError: If any question is already in the contest.
            InvalidContestQuestionDataError: If any question fails validation.
            PermissionDeniedError: If user lacks permission to manage the contest.
        """
        if not request.questions:
            return []

        # Step 1: Validate contest exists
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Step 2: Check user has permission to manage contest
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Step 3: Validate all questions and build DTOs
        if self.question_repository is None:
            raise InvalidContestError("Question repository not initialized in service")

        dto_list = []
        seen_question_ids: set[UUID] = set()
        seen_orders: set[int] = set()
        existing_orders = await self.repository.get_ordered_question_orders_for_contest(
            contest_id
        )

        for question_request in request.questions:
            if question_request.question_id in seen_question_ids:
                raise QuestionAlreadyInContestError(
                    str(question_request.question_id), str(contest_id)
                )
            seen_question_ids.add(question_request.question_id)

            # Validate question exists
            await self.question_repository.get_question_or_raise(
                question_request.question_id
            )

            # Validate question not already in contest
            is_duplicate = await self.repository.is_question_in_contest(
                contest_id, question_request.question_id
            )
            if is_duplicate:
                raise QuestionAlreadyInContestError(
                    str(question_request.question_id), str(contest_id)
                )

            # Validate business rules (order, duration, score)
            self.validator.validate_question_order(question_request.order)

            if question_request.order in seen_orders:
                raise DuplicateQuestionOrderError(
                    question_request.order,
                    str(contest_id),
                )
            if question_request.order in existing_orders:
                raise DuplicateQuestionOrderError(
                    question_request.order,
                    str(contest_id),
                )
            seen_orders.add(question_request.order)

            self.validator.validate_question_duration(question_request.duration)
            self.validator.validate_question_score(question_request.score)

            # Build DTO
            dto = build_add_contest_question_dto(question_request, contest_id, user_id)
            dto_list.append(dto)

        # Step 4: Batch add to repository
        contest_questions = await self.repository.add_questions_to_contest(dto_list)

        logger.info(
            f"Added {len(request.questions)} questions to contest {contest_id} by user {user_id}"
        )

        return [to_contest_question_response(cq) for cq in contest_questions]

    @cache_delete(
        key_builder=lambda self, contest_id, request, user_id: [
            f"contest:{contest_id}:questions:*",
        ]
    )
    async def remove_questions_from_contest(
        self,
        contest_id: UUID,
        request: RemoveContestQuestionRequest,
        user_id: UUID,
    ) -> None:
        """
        Remove multiple questions from a contest in batch.

        This method orchestrates batch removal of questions by verifying permissions
        and checking existence before deletion.

        Permission Check:
            Only users who can manage the contest can remove questions.

        Validation Workflow:
            1. Contest existence check
            2. Permission check
            3. Remove questions

        Args:
            contest_id: UUID of the contest.
            request: RemoveContestQuestionRequest containing list of question_ids.
            user_id: UUID of the authenticated user performing the operation.

        Returns:
            None

        Raises:
            ContestNotFoundError: If contest does not exist.
            QuestionNotInContestError: If any question is not in the contest.
            PermissionDeniedError: If user lacks permission to manage the contest.
        """
        if not request.question_ids:
            return

        # Step 1: Validate contest exists
        contest = await self.repository.get_contest_or_raise(contest_id)

        # Step 2: Check user has permission to manage contest
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        # Step 3: Validate all questions are in contest
        for question_id in request.question_ids:
            is_in_contest = await self.repository.is_question_in_contest(
                contest_id, question_id
            )
            if not is_in_contest:
                raise QuestionNotInContestError(str(question_id), str(contest_id))

        # Step 4: Batch remove from repository
        await self.repository.remove_questions_from_contest(
            contest_id, request.question_ids
        )

        logger.info(
            f"Removed {len(request.question_ids)} questions from contest {contest_id} by user {user_id}"
        )

    async def _get_contest_question_for_update(
        self,
        contest_id: UUID,
        question_id: UUID,
        user_id: UUID,
    ) -> Question:
        """Resolve a contest-scoped question after permission and linkage checks."""
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        is_in_contest = await self.repository.is_question_in_contest(
            contest_id, question_id
        )
        if not is_in_contest:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

        if self.question_repository is None:
            raise InvalidContestError("Question repository not initialized in service")

        return await self.question_repository.get_question_or_raise(question_id)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, *args, **kwargs: [
            f"contest:{contest_id}:questions:*"
        ]
    )
    async def update_contest_question_metadata(
        self,
        contest_id: UUID,
        question_id: UUID,
        payload: UpdateQuestionMetadataRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Update metadata for a question linked to a contest."""
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        QuestionValidator.validate_metadata_update(payload)
        update_dto = build_metadata_update_dto(payload)
        apply_question_updates(question, update_dto)

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, *args, **kwargs: [
            f"contest:{contest_id}:questions:*"
        ]
    )
    async def add_testcases_to_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        payload: AddQuestionTestCasesRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Append testcases to a contest question."""

        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        QuestionValidator.validate_testcases_format(payload.testcases)
        testcase_dtos = build_appended_testcase_dtos(
            payload.testcases,
            starting_order=len(question.testcases),
        )
        question.testcases.extend(
            build_testcase_entities(testcase_dtos, created_by=user_id)
        )

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, *args, **kwargs: [
            f"contest:{contest_id}:questions:*"
        ]
    )
    async def remove_testcases_from_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        payload: RemoveQuestionTestCasesRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Remove testcases from a contest question."""

        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        QuestionValidator.validate_unique_testcase_ids(payload.testcase_ids)
        existing_ids = {testcase.id for testcase in question.testcases}
        QuestionValidator.validate_question_testcases_exist(
            existing_ids,
            payload.testcase_ids,
        )

        remove_ids = set(payload.testcase_ids)
        question.testcases = [
            testcase for testcase in question.testcases if testcase.id not in remove_ids
        ]

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, *args, **kwargs: [
            f"contest:{contest_id}:questions:*"
        ]
    )
    async def update_testcases_of_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        payload: AddQuestionTestCasesRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Replace all testcases for a contest question."""
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        QuestionValidator.validate_testcases_format(payload.testcases)
        testcase_dtos = build_create_testcase_dtos(payload.testcases)
        question.testcases = build_testcase_entities(testcase_dtos, created_by=user_id)

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self,
        contest_id,
        question_id,
        testcase_id,
        *args,
        **kwargs: [f"contest:{contest_id}:questions:*"]
    )
    async def update_testcase_of_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        testcase_id: UUID,
        payload: UpdateQuestionTestCaseRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Update one testcase of a contest question by testcase ID."""
        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        testcase_to_update = next(
            (testcase for testcase in question.testcases if testcase.id == testcase_id),
            None,
        )
        if testcase_to_update is None:
            raise InvalidQuestionError(
                f"Testcase {testcase_id} is not found in question {question_id}"
            )

        if payload.input is not None:
            testcase_to_update.input = payload.input
        if payload.output is not None:
            testcase_to_update.output = payload.output
        if payload.is_hidden is not None:
            testcase_to_update.is_hidden = payload.is_hidden
        if payload.weight is not None:
            testcase_to_update.weight = payload.weight
        if payload.order is not None:
            testcase_to_update.order = payload.order

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, *args, **kwargs: [
            f"contest:{contest_id}:questions:*"
        ]
    )
    async def add_templates_to_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        payload: AddQuestionTemplatesRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Append templates to a contest question."""
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        language_ids = [template.language_id for template in payload.templates]
        QuestionValidator.validate_unique_template_language_ids(language_ids)

        existing_language_ids = {
            template.language_id for template in question.templates
        }
        for language_id in language_ids:
            if language_id in existing_language_ids:
                raise TemplateAlreadyExistsError(question_id, language_id)

        question.templates.extend(
            [
                QuestionTemplate(
                    language_id=template.language_id,
                    starter_code=template.starter_code,
                    driver_code=template.driver_code,
                    solution_code=template.solution_code,
                )
                for template in payload.templates
            ]
        )

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, *args, **kwargs: [
            f"contest:{contest_id}:questions:*"
        ]
    )
    async def remove_templates_from_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        payload: RemoveQuestionTemplatesRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Remove templates from a contest question."""

        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        QuestionValidator.validate_unique_template_language_ids(payload.language_ids)
        existing_language_ids = {
            template.language_id for template in question.templates
        }
        QuestionValidator.validate_question_template_languages_exist(
            existing_language_ids,
            payload.language_ids,
        )

        remove_languages = set(payload.language_ids)
        question.templates = [
            template
            for template in question.templates
            if template.language_id not in remove_languages
        ]

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, *args, **kwargs: [
            f"contest:{contest_id}:questions:*"
        ]
    )
    async def update_templates_of_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        payload: AddQuestionTemplatesRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Replace all templates for a contest question."""
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        language_ids = [template.language_id for template in payload.templates]
        QuestionValidator.validate_unique_template_language_ids(language_ids)

        question.templates = [
            QuestionTemplate(
                language_id=template.language_id,
                starter_code=template.starter_code,
                driver_code=template.driver_code,
                solution_code=template.solution_code,
            )
            for template in payload.templates
        ]

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self,
        contest_id,
        question_id,
        template_id,
        *args,
        **kwargs: [f"contest:{contest_id}:questions:*"]
    )
    async def update_template_of_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        template_id: UUID,
        payload: UpdateQuestionTemplateRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Update one template of a contest question by template ID."""
        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        template_to_update = next(
            (template for template in question.templates if template.id == template_id),
            None,
        )
        if template_to_update is None:
            raise InvalidQuestionError(
                f"Template {template_id} is not found in question {question_id}"
            )

        if payload.language_id is not None:
            duplicate_language = any(
                template.id != template_id
                and template.language_id == payload.language_id
                for template in question.templates
            )
            if duplicate_language:
                raise TemplateAlreadyExistsError(question_id, payload.language_id)
            template_to_update.language_id = payload.language_id

        if payload.starter_code is not None:
            template_to_update.starter_code = payload.starter_code
        if payload.driver_code is not None:
            template_to_update.driver_code = payload.driver_code
        if payload.solution_code is not None:
            template_to_update.solution_code = payload.solution_code

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, *args, **kwargs: [
            f"contest:{contest_id}:questions:*"
        ]
    )
    async def add_allowed_languages_to_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        payload: AddQuestionAllowedLanguagesRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Add allowed languages to a contest question."""
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        if len(set(payload.language_ids)) != len(payload.language_ids):
            raise InvalidQuestionError("Duplicate allowed language IDs are not allowed")

        current_language_ids = [mapping.language_id for mapping in question.languages]
        duplicates = [
            language_id
            for language_id in payload.language_ids
            if language_id in current_language_ids
        ]
        if duplicates:
            raise InvalidQuestionError(
                f"Language ID {duplicates[0]} is already in allowed languages"
            )

        updated_language_ids = current_language_ids + payload.language_ids
        apply_question_updates(
            question,
            UpdateQuestionData(allowed_languages=updated_language_ids),
        )

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, *args, **kwargs: [
            f"contest:{contest_id}:questions:*"
        ]
    )
    async def remove_allowed_languages_from_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        payload: RemoveQuestionAllowedLanguagesRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Remove allowed languages from a contest question."""
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        if len(set(payload.language_ids)) != len(payload.language_ids):
            raise InvalidQuestionError("Duplicate allowed language IDs are not allowed")

        current_language_ids = [mapping.language_id for mapping in question.languages]
        missing = [
            language_id
            for language_id in payload.language_ids
            if language_id not in current_language_ids
        ]
        if missing:
            raise InvalidQuestionError(
                f"Language ID {missing[0]} is not in allowed languages"
            )

        remove_set = set(payload.language_ids)
        remaining_language_ids = [
            language_id
            for language_id in current_language_ids
            if language_id not in remove_set
        ]
        QuestionValidator.validate_allowed_languages(remaining_language_ids)

        apply_question_updates(
            question,
            UpdateQuestionData(allowed_languages=remaining_language_ids),
        )

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, *args, **kwargs: [
            f"contest:{contest_id}:questions:*"
        ]
    )
    async def update_allowed_languages_of_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        payload: UpdateQuestionAllowedLanguagesRequest,
        user_id: UUID,
    ) -> QuestionResponse:
        """Replace allowed languages of a contest question."""
        contest = await self.repository.get_contest_or_raise(contest_id)
        await self.guard.check_manage_contest(user_id=user_id, contest=contest)

        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        if len(set(payload.language_ids)) != len(payload.language_ids):
            raise InvalidQuestionError("Duplicate allowed language IDs are not allowed")
        QuestionValidator.validate_allowed_languages(payload.language_ids)

        apply_question_updates(
            question,
            UpdateQuestionData(allowed_languages=payload.language_ids),
        )

        assert self.question_repository is not None
        updated_question = await self.question_repository.update_question(question)
        return QuestionResponse.from_question(updated_question)

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
