import uuid
from typing import Literal, Optional
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.core.guards.contest import ContestOperationGuard
from app.core.logger import logger
from app.exceptions.contest import (
    ContestNotFoundError,
    DuplicateQuestionOrderError,
    QuestionAlreadyInContestError,
    QuestionNotInContestError,
)
from app.exceptions.question import InvalidQuestionError
from app.mappers.contest_question import (
    build_add_contest_question_dto,
    to_contest_question_response,
)
from app.mappers.question import (
    apply_question_updates,
    build_template_dto,
    build_update_question_dto,
    build_update_testcase_dtos,
)
from app.models.question import Question
from app.repositories.bank import BankRepository
from app.repositories.contest import ContestRepository
from app.repositories.dto import (
    ContestQuestionFilters,
    PaginationParams,
)
from app.repositories.dto.contest_question import AddContestQuestionData
from app.repositories.dto.question import CreateQuestionTemplateData
from app.repositories.language import LanguageRepository
from app.repositories.question import QuestionRepository
from app.schema.contest import (
    AddContestQuestionRequest,
    AddContestQuestionsRequest,
    ContestBankCloneRequest,
    ContestQuestionResponse,
    RemoveContestQuestionRequest,
    ReorderContestQuestionsRequest,
)
from app.schema.question import (
    ContestQuestionsListResponse,
    QuestionListSummaryResponse,
    QuestionResponse,
    QuestionUpdate,
)
from app.utils.enums import (
    ContestQuestionSortBy,
    ContestStatus,
    QuestionDifficulty,
    SortOrder,
)
from app.utils.question_clone import deep_copy_question_for_clone
from app.validators.bank import BankValidator
from app.validators.contest import ContestValidator
from app.validators.question import QuestionValidator


class ContestQuestionService:
    """Service layer for contest question management operations."""

    def __init__(
        self,
        repository: ContestRepository,
        guard: ContestOperationGuard,
        validator: ContestValidator,
        question_repository: QuestionRepository,
        language_repository: LanguageRepository,
        bank_repository: BankRepository,
    ):
        """
        Initialize the ContestQuestionService.

        Args:
            repository: Repository for contest data access.
            guard: Operation guard for permission checks.
            validator: Validator for contest-specific business rules.
            question_repository: Repository for platform-level question access.
            language_repository: Repository for platform-level language validation.
            bank_repository: Repository for bank data access.
        """
        self.repository = repository
        self.guard = guard
        self.validator = validator
        self.question_repository = question_repository
        self.language_repository = language_repository
        self.bank_repository = bank_repository

    async def _verify_contest_access(
        self,
        contest_id: UUID,
        user_id: UUID,
        permission_level: Literal["read", "manage"] = "read",
    ) -> None:
        """
        Verify contest exists, not deleted, and user has appropriate access.

        Args:
            contest_id: UUID of the contest.
            user_id: UUID of the user requesting access.
            permission_level: Either "read" or "manage". Defaults to "read".

        Raises:
            ContestNotFoundError: If contest doesn't exist or is deleted.
            PermissionDeniedError: If user lacks required permission.
        """
        contest = await self.repository.get_contest_or_raise(contest_id)
        if contest.status == ContestStatus.DELETED:
            raise ContestNotFoundError(str(contest_id))

        if permission_level == "manage":
            await self.guard.check_manage_contest(user_id=user_id, contest=contest)
        else:
            await self.guard.check_read_contest(user_id=user_id, contest=contest)

    async def _verify_question_in_contest(
        self, contest_id: UUID, question_id: UUID
    ) -> None:
        """
        Verify that a question is linked to a contest.

        Args:
            contest_id: UUID of the contest.
            question_id: UUID of the question.

        Raises:
            QuestionNotInContestError: If question is not in contest.
        """
        is_in_contest = await self.repository.is_question_in_contest(
            contest_id, question_id
        )
        if not is_in_contest:
            raise QuestionNotInContestError(str(question_id), str(contest_id))

    @cache_get(
        key_builder=lambda self, contest_id, user_id, search_term=None, difficulty=None, language_id=None, tag_id=None, tag_name=None, sort_by=None, sort_order="asc", skip=0, limit=20: (
            f"contest:{contest_id}:questions:user:{user_id}:search:{search_term}:difficulty:{difficulty}:language:{language_id}:tag_id:{tag_id}:tag_name:{tag_name}:sort_by:{sort_by}:sort_order:{sort_order}:skip:{skip}:limit:{limit}"
        ),
        ttl=300,
    )
    async def get_contest_questions(
        self,
        contest_id: UUID,
        user_id: UUID,
        search_term: str | None = None,
        difficulty: QuestionDifficulty | None = None,
        language_id: int | None = None,
        tag_id: Optional[UUID] = None,
        tag_name: Optional[str] = None,
        sort_by: ContestQuestionSortBy | None = None,
        sort_order: SortOrder | None = SortOrder.ASC,
        skip: int = 0,
        limit: int = 20,
    ) -> ContestQuestionsListResponse:
        """
        Retrieve a paginated list of summary questions for a contest.

        Args:
            contest_id: UUID of the contest.
            user_id: UUID of the user requesting the questions.
            search_term: Optional text search for question title.
            difficulty: Optional filter for question difficulty level.
            language_id: Optional filter for platform language support.
            tag_id: Optional filter for question tags.
            skip: Number of records to skip for pagination.
            limit: Maximum number of records to return.

        Returns:
            ContestQuestionsListResponse: Paginated results with metadata and statistics.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            PermissionDeniedError: If the user lacks read permission for the contest.
        """
        await self._verify_contest_access(contest_id, user_id, "read")

        filters = ContestQuestionFilters(
            search_term=search_term,
            difficulty=difficulty,
            language_id=language_id,
            tag_id=tag_id,
            tag_name=tag_name,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        result = await self.repository.get_contest_questions_paginated(
            contest_id, PaginationParams(skip=skip, limit=limit), filters
        )

        return ContestQuestionsListResponse(
            questions=[
                QuestionListSummaryResponse.from_question(question)
                for question in result.items
            ],
            easy_count=result.easy_count,
            medium_count=result.medium_count,
            hard_count=result.hard_count,
            total_count=result.total,
        )

    @cache_get(
        key_builder=lambda self, contest_id, question_id, user_id: (
            f"contest:{contest_id}:questions:item:{question_id}:user:{user_id}"
        ),
        ttl=300,
    )
    async def get_contest_question(
        self, contest_id: UUID, question_id: UUID, user_id: UUID
    ) -> QuestionResponse:
        """
        Retrieve details of a specific question linked to a contest.

        Args:
            contest_id: UUID of the contest.
            question_id: UUID of the question to retrieve.
            user_id: UUID of the requesting user.

        Returns:
            QuestionResponse: Detailed question data.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            QuestionNotInContestError: If the question is not linked to the specified contest.
            PermissionDeniedError: If the user lacks read permission.
        """
        await self._verify_contest_access(contest_id, user_id, "read")
        await self._verify_question_in_contest(contest_id, question_id)

        question = await self.question_repository.get_question_or_raise(question_id)
        return QuestionResponse.from_question(question)

    @cache_delete(
        key_builder=lambda self, contest_id, request, user_id: [
            f"contest:{contest_id}*",
            "contests:*",
        ]
    )
    async def add_questions_to_contest(
        self,
        contest_id: UUID,
        request: AddContestQuestionsRequest,
        user_id: UUID,
    ) -> list[ContestQuestionResponse]:
        """
        Add multiple existing platform questions to a contest.

        Validates question existence, uniqueness within the contest, and order constraints.

        Args:
            contest_id: UUID of the target contest.
            request: DTO containing question IDs and their metadata (order, score, etc).
            user_id: UUID of the authenticated user performing the operation.

        Returns:
            list[ContestQuestionResponse]: List of created contest-question relationships.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            InvalidQuestionError: If the payload contains duplicate question IDs.
            QuestionAlreadyInContestError: If a question is already linked to the contest.
            DuplicateQuestionOrderError: If the specified order conflicts with existing ones.
            PermissionDeniedError: If the user lacks management permissions for the contest.
        """
        await self._verify_contest_access(contest_id, user_id, "manage")

        if not request.questions:
            return []

        # Step 1: Validate batch size
        self.validator.validate_batch_add_limit(len(request.questions))

        # Step 2: Fetch existing contest questions
        existing_contest_questions = (
            await self.repository.get_ordered_question_orders_for_contest(contest_id)
        )
        existing_ids = {cq.question_id for cq in existing_contest_questions}
        existing_orders = {cq.order for cq in existing_contest_questions}

        # Step 3: Calculate base order and validate all questions
        dtos = []
        seen_question_ids: set[UUID] = set()
        max_order = await self.repository.get_max_question_order(contest_id)
        next_order = max_order + 1

        for q_req in request.questions:
            # 3a. Check duplicate ID in payload
            if q_req.question_id in seen_question_ids:
                raise InvalidQuestionError(
                    f"Duplicate question ID in request: {q_req.question_id}"
                )
            seen_question_ids.add(q_req.question_id)

            # 3b. Verify question exists in platform
            await self.question_repository.get_question_or_raise(q_req.question_id)

            # 3c. Verify question is not already in contest
            if q_req.question_id in existing_ids:
                raise QuestionAlreadyInContestError(
                    str(q_req.question_id), str(contest_id)
                )

            # 3d. Check order duplication (within payload + existing)
            order = q_req.order
            if order is None:
                while next_order in existing_orders:
                    next_order += 1
                order = next_order
                next_order += 1
            elif order in existing_orders:
                raise DuplicateQuestionOrderError(order, str(contest_id))

            existing_orders.add(order)
            if order >= next_order:
                next_order = order + 1

            # 3e. Map to DTO
            dto = build_add_contest_question_dto(
                q_req, contest_id=contest_id, created_by=user_id, order=order
            )
            dtos.append(dto)

        # Step 4: Batch insert
        results = await self.repository.add_questions_to_contest(dtos)

        # Step 5: Log and return
        logger.info(
            f"Batch added {len(results)} questions to contest {contest_id} by user {user_id}"
        )
        return [to_contest_question_response(cq) for cq in results]

    @cache_delete(
        key_builder=lambda self, contest_id, request, user_id: [
            f"contest:{contest_id}*",
            "contests:*",
        ]
    )
    async def remove_questions_from_contest(
        self,
        contest_id: UUID,
        request: RemoveContestQuestionRequest,
        user_id: UUID,
    ) -> None:
        """
        Remove multiple questions from a contest.

        Args:
            contest_id: UUID of the target contest.
            request: DTO containing the list of question IDs to remove.
            user_id: UUID of the authenticated user performing the operation.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            QuestionNotInContestError: If any of the specified questions are not in the contest.
            PermissionDeniedError: If the user lacks management permissions for the contest.
        """
        await self._verify_contest_access(contest_id, user_id, "manage")

        if not request.question_ids:
            return

        # Verify all questions are linked to the contest
        for question_id in request.question_ids:
            await self._verify_question_in_contest(contest_id, question_id)

        # Perform batch removal
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
        """
        Resolve a contest-linked question after permission and linkage validation.

        Args:
            contest_id: UUID of the contest.
            question_id: UUID of the question to resolve.
            user_id: UUID of the user performing the request.

        Returns:
            Question: The validated ORM question entity.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            QuestionNotInContestError: If the question is not linked to the contest.
            PermissionDeniedError: If the user lacks management permissions.
        """
        await self._verify_contest_access(contest_id, user_id, "manage")
        await self._verify_question_in_contest(contest_id, question_id)

        return await self.question_repository.get_question_or_raise(question_id)

    @cache_delete(
        key_builder=lambda self, contest_id, question_id, update_data, user_id: [
            f"contest:{contest_id}*",
            "contests:*",
        ]
    )
    async def update_contest_question(
        self,
        contest_id: UUID,
        question_id: UUID,
        update_data: QuestionUpdate,
        user_id: UUID,
    ) -> QuestionResponse:
        """
        Perform an atomic, comprehensive update of a contest question.

        Handles metadata (title, difficulty), limits, tags, allowed languages,
        starter code templates, and test cases in a single operation.

        Args:
            contest_id: UUID of the contest.
            question_id: UUID of the question to update.
            update_data: DTO containing all fields to be updated.
            user_id: UUID of the authenticated user.

        Returns:
            QuestionResponse: The fully updated question data.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            QuestionNotInContestError: If the question is not linked to the contest.
            PermissionDeniedError: If the user lacks management permissions.
            InvalidQuestionError: If any of the update fields fail domain validation rules.
        """
        question = await self._get_contest_question_for_update(
            contest_id, question_id, user_id
        )

        # Validation
        if update_data.testcases is not None:
            QuestionValidator.validate_testcases_format(update_data.testcases)
        QuestionValidator.validate_limits(
            update_data.time_limit_ms, update_data.memory_limit_mb
        )
        if update_data.allowed_languages is not None:
            QuestionValidator.validate_allowed_languages(update_data.allowed_languages)
        if update_data.templates is not None:
            QuestionValidator.validate_unique_template_language_ids(
                [template.language_id for template in update_data.templates]
            )

        await QuestionValidator.validate_platform_languages_exist(
            self.language_repository,
            allowed_language_ids=update_data.allowed_languages or [],
            template_language_ids=[
                t.language_id for t in (update_data.templates or [])
            ],
        )

        # Build DTOs
        testcase_dtos = build_update_testcase_dtos(update_data.testcases)

        template_dtos: list[CreateQuestionTemplateData] | None = None
        if update_data.templates is not None:
            template_dtos = []
            for template in update_data.templates:
                template_id = uuid.uuid4()
                mapped_template_dto = build_template_dto(
                    template_id=template_id,
                    template=template,
                    solution_code_value=template.solution_code,
                )
                template_dtos.append(mapped_template_dto)

        update_dto = build_update_question_dto(
            update_data,
            testcase_dtos=testcase_dtos,
            template_dtos=template_dtos,
        )

        # Apply and persist
        apply_question_updates(question, update_dto)
        updated_question = await self.question_repository.update_question(question)

        return QuestionResponse.from_question(updated_question)

    @cache_delete(
        key_builder=lambda self, contest_id, request, user_id: [
            f"contest:{contest_id}*",
            "contests:*",
        ]
    )
    async def reorder_contest_questions(
        self,
        contest_id: UUID,
        request: ReorderContestQuestionsRequest,
        user_id: UUID,
    ) -> None:
        """
        Reorder questions within a contest.

        Validates that all questions exist in the contest and that the new orders
        do not conflict or leave gaps (enforces sequential ordering from 1 to N).

        Args:
            contest_id: UUID of the contest.
            request: DTO containing the list of question IDs and their new orders.
            user_id: UUID of the authenticated user.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            QuestionNotInContestError: If any of the questions are not in the contest.
            PermissionDeniedError: If the user lacks management permissions.
            InvalidContestError: If the reorder request results in invalid ordering.
        """
        await self._verify_contest_access(contest_id, user_id, "manage")

        if not request.reorders:
            return

        # Fetch existing questions to validate IDs and current state
        existing_questions = (
            await self.repository.get_ordered_question_orders_for_contest(contest_id)
        )
        existing_q_ids = {cq.question_id for cq in existing_questions}

        # 1. Validate all request IDs belong to the contest
        request_q_ids = {r.question_id for r in request.reorders}
        self.validator.validate_questions_in_contest(
            request_q_ids, existing_q_ids, contest_id
        )

        # 2. Map existing questions by ID for easy lookup
        order_map = {cq.question_id: cq.order for cq in existing_questions}

        # 3. Apply changes to the map
        for r in request.reorders:
            order_map[r.question_id] = r.order

        # 4. Validate the resulting order set (should be 1 to N without duplicates)
        self.validator.validate_sequential_ordering(
            list(order_map.values()), len(existing_questions)
        )

        # 5. Build reorder list for repository
        reorder_data = [(qid, order) for qid, order in order_map.items()]

        # 6. Execute bulk update
        await self.repository.reorder_questions_in_contest(contest_id, reorder_data)

        logger.info(f"User {user_id} reordered questions in contest {contest_id}")

    @cache_delete(
        key_builder=lambda self, contest_id, request, user_id: [
            f"contest:{contest_id}*",
            "contests:*",
        ]
    )
    async def clone_questions_from_bank(
        self,
        contest_id: UUID,
        request: ContestBankCloneRequest,
        user_id: UUID,
    ) -> list[ContestQuestionResponse]:
        """
        Clone questions from a bank into a contest.

        Args:
            contest_id: UUID of the target contest.
            request: DTO containing bank ID and selection criteria.
            user_id: UUID of the authenticated user.

        Returns:
            list[ContestQuestionResponse]: List of created contest-question relationships.

        Raises:
            ContestNotFoundError: If the contest does not exist or is deleted.
            BankNotFoundError: If the source bank does not exist.
            PermissionDeniedError: If the user lacks necessary permissions.
        """
        await self._verify_contest_access(contest_id, user_id, "manage")

        # Resolve and validate bank
        bank = await self.bank_repository.get_bank_or_raise(
            request.bank_id, load_relations=True
        )
        BankValidator.check_read_bank(user_id, bank)

        # Retrieve source questions
        if request.copy_all:
            source_questions = (
                await self.bank_repository.get_all_question_entities_in_bank(
                    request.bank_id
                )
            )
        elif request.questions:
            question_ids = [q.question_id for q in request.questions]
            source_questions = (
                await self.bank_repository.get_question_entities_in_bank_by_ids(
                    request.bank_id, question_ids
                )
            )
        else:
            return []

        if not source_questions:
            return []

        # Deep copy questions and track source mapping
        cloned_to_source_map = {}
        cloned_questions: list[Question] = []
        for src_q in source_questions:
            cloned_q = deep_copy_question_for_clone(src_q, created_by=user_id)
            cloned_questions.append(cloned_q)
            cloned_to_source_map[cloned_q] = src_q.id

        # Bulk create cloned questions
        created_questions = await self.question_repository.bulk_create_questions(
            cloned_questions
        )

        # Prepare contest-question links
        max_order = await self.repository.get_max_question_order(contest_id)
        next_order = max_order + 1

        config_map = {q.question_id: q for q in (request.questions or [])}
        dtos: list[AddContestQuestionData] = []

        for created_q in created_questions:
            source_id = cloned_to_source_map[created_q]
            config = config_map.get(source_id)

            score = (
                config.score if config and config.score is not None else request.score
            )
            duration = (
                config.duration
                if config and config.duration is not None
                else request.duration
            )

            q_req = AddContestQuestionRequest(
                question_id=created_q.id,
                order=next_order,
                score=score,
                duration=duration,
            )
            dto = build_add_contest_question_dto(
                q_req, contest_id=contest_id, created_by=user_id, order=next_order
            )
            dtos.append(dto)
            next_order += 1

        # Batch insert into contest
        results = await self.repository.add_questions_to_contest(dtos)

        # Log and return
        logger.info(
            f"Cloned {len(results)} questions from bank {request.bank_id} to contest {contest_id} by user {user_id}"
        )
        return [to_contest_question_response(cq) for cq in results]
