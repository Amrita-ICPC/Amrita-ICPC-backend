import asyncio
import uuid
from uuid import UUID

import httpx

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.core.config import config
from app.core.guards.question import QuestionOperationGuard
from app.core.storage import CodeStorageService
from app.exceptions.question import (
    CodeStorageError,
    InvalidQuestionError,
    Judge0ServiceError,
)
from app.repositories.dto.question import (
    CreateQuestionData,
    CreateQuestionTemplateData,
    CreateQuestionTestCaseData,
    UpdateQuestionData,
)
from app.repositories.language import LanguageRepository
from app.repositories.question import QuestionRepository
from app.schema.question import (
    Judge0LanguageResponse,
    PlatformLanguageCreateRequest,
    PlatformLanguageResponse,
    QuestionCreate,
    QuestionResponse,
    QuestionUpdate,
)
from app.validators.question import QuestionValidator


class QuestionService:
    """Service layer for question management operations.

    This service coordinates question-related business logic across repository,
    guard, validator, and storage layers. It keeps routes thin by handling
    validation, permission checks, DTO orchestration, storage interactions, and
    cache management in one place.

    Responsibilities:
        - Create/update/delete question aggregates
        - Validate limits, testcase structure, and language mappings
        - Enforce read/manage permissions through guard checks
        - Store and retrieve template code payloads from object storage
        - Manage read-through and write-through cache behavior
        - Integrate with Judge0 language catalog and platform language mappings

    Dependencies:
        - QuestionRepository: Question persistence operations
        - LanguageRepository: Platform language catalog operations
        - QuestionOperationGuard: Domain permission checks
        - QuestionValidator: Business rule validation
        - CodeStorageService: MinIO-backed code payload storage
    """

    def __init__(
        self,
        repository: QuestionRepository,
        language_repository: LanguageRepository,
        guard: QuestionOperationGuard,
        validator: QuestionValidator,
        code_storage_service: CodeStorageService,
    ):
        self.repository = repository
        self.language_repository = language_repository
        self.guard = guard
        self.validator = validator
        self.code_storage_service = code_storage_service

    def _get_question_cache_keys(self, question_id: UUID) -> list[str]:
        """Build cache patterns to invalidate for question mutations.

        Args:
            question_id: Question identifier whose cached views must be invalidated.

        Returns:
            Cache key/pattern list covering direct and user-scoped entries.
        """
        return [f"question:{question_id}", f"question:{question_id}:*"]

    @staticmethod
    def _is_storage_object_key(value: str | None) -> bool:
        """Check whether a value looks like a storage object key.

        Args:
            value: Potential plain code content or storage key.

        Returns:
            True when value is a MinIO object-key path, otherwise False.
        """
        return bool(value and value.startswith("code/"))

    async def _resolve_code_field(self, value: str | None) -> str | None:
        """Resolve object-key values to code text.

        Args:
            value: Raw field value from template code columns.

        Returns:
            Plain code text when value is a storage key, otherwise original value.

        Raises:
            CodeStorageError: If storage lookup fails.
        """
        if not self._is_storage_object_key(value):
            return value
        assert value is not None
        try:
            return await self.code_storage_service.get_code(value)
        except Exception as error:
            raise CodeStorageError(
                f"Failed to fetch code payload from storage: {error}"
            ) from error

    async def _hydrate_question_template_codes(
        self, question_response: QuestionResponse
    ) -> QuestionResponse:
        """Hydrate template code fields in a question response.

        Args:
            question_response: Response DTO containing template code fields.

        Returns:
            Same DTO with starter/driver/solution fields resolved to code text.

        Raises:
            CodeStorageError: If any object-key fetch fails.
        """
        for template in question_response.templates:
            starter_code, driver_code, solution_code = await asyncio.gather(
                self._resolve_code_field(template.starter_code),
                self._resolve_code_field(template.driver_code),
                self._resolve_code_field(template.solution_code),
            )
            template.starter_code = starter_code or ""
            template.driver_code = driver_code
            template.solution_code = solution_code
        return question_response

    @cache_get(
        key_builder=lambda self: "judge0:languages",
        ttl=300,
    )
    async def get_judge0_languages(self) -> list[Judge0LanguageResponse]:
        """Fetch and normalize available Judge0 languages.

        Returns:
            List of normalized Judge0 languages.

        Raises:
            Judge0ServiceError: If configuration is missing, request fails, or
                payload format is invalid.
        """
        base_url = (config.JUDGE0_API_URL or "").rstrip("/")
        if not base_url:
            raise Judge0ServiceError("JUDGE0_API_URL is not configured")
        endpoint = (
            base_url if base_url.endswith("/languages") else f"{base_url}/languages"
        )

        headers: dict[str, str] = {"Accept": "application/json"}
        if config.JUDGE0_API_KEY:
            headers["X-Auth-Token"] = config.JUDGE0_API_KEY

        try:
            timeout = config.JUDGE0_API_TIMEOUT or 30
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    endpoint,
                    headers=headers,
                )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as error:
            raise Judge0ServiceError(f"Judge0 request failed: {error}") from error
        except ValueError as error:
            raise Judge0ServiceError("Judge0 returned invalid JSON response") from error

        if not isinstance(payload, list):
            raise Judge0ServiceError("Judge0 returned an unexpected payload format")

        languages: list[Judge0LanguageResponse] = []
        for item in payload:
            if isinstance(item, dict) and "id" in item and "name" in item:
                languages.append(
                    Judge0LanguageResponse(id=item["id"], name=item["name"])
                )

        return languages

    @cache_delete(
        key_builder=lambda self, payload: "platform:languages",
    )
    async def create_platform_language(
        self, payload: PlatformLanguageCreateRequest
    ) -> PlatformLanguageResponse:
        """Create a platform language mapping from Judge0.

        Args:
            payload: Judge0 language ID and optional local mapping metadata.

        Returns:
            Persisted platform language mapping.

        Raises:
            InvalidQuestionError: If Judge0 language does not exist, ID already
                exists locally, or slug conflicts.
            Judge0ServiceError: If Judge0 language retrieval fails.
        """
        judge0_languages = await self.get_judge0_languages()
        match = next(
            (
                language
                for language in judge0_languages
                if language.id == payload.judge0_language_id
            ),
            None,
        )
        if match is None:
            raise InvalidQuestionError(
                f"Judge0 language id {payload.judge0_language_id} was not found"
            )

        existing = await self.language_repository.get_by_id(payload.judge0_language_id)
        if existing is not None:
            raise InvalidQuestionError(
                f"Language with Judge0 id {payload.judge0_language_id} already exists"
            )

        slug_value = (payload.slug or match.name.lower().replace(" ", "-")).strip()
        duplicate_slug = await self.language_repository.get_by_slug(slug_value)
        if duplicate_slug is not None:
            raise InvalidQuestionError(f"Language slug '{slug_value}' already exists")

        created = await self.language_repository.create_language(
            language_id=match.id,
            name=match.name,
            slug=slug_value,
            file_extension=payload.file_extension,
            monaco_language=payload.monaco_language,
        )
        return PlatformLanguageResponse.model_validate(created)

    @cache_get(
        key_builder=lambda self: "platform:languages",
        ttl=300,
    )
    async def get_platform_languages(self) -> list[PlatformLanguageResponse]:
        """Return platform language mappings.

        Returns:
            List of platform language mappings derived from Judge0 IDs.
        """
        languages = await self.language_repository.list_languages()
        return [
            PlatformLanguageResponse.model_validate(language) for language in languages
        ]

    @cache_set(
        key_builder=lambda result: f"question:{result.id}:user:{result.created_by}",
        ttl=300,
        from_result=True,
    )
    async def create_question(
        self, question_data: QuestionCreate, user_id: UUID
    ) -> QuestionResponse:
        """Create a question aggregate and store template solution payloads.

        Args:
            question_data: Request payload with question fields, testcases, and templates.
            user_id: Authenticated user creating the question.

        Returns:
            Created question response.

        Raises:
            InvalidQuestionError: If validation fails.
            CodeStorageError: If template solution upload fails.
            Exception: Re-raises underlying persistence/storage errors after rollback.
        """
        uploaded_keys: list[str] = []
        try:
            self.validator.validate_testcases_format(question_data.testcases)
            self.validator.validate_limits(
                question_data.time_limit_ms, question_data.memory_limit_mb
            )
            self.validator.validate_allowed_languages(question_data.allowed_languages)

            question_id = uuid.uuid4()

            await self.validator.validate_platform_languages_exist(
                self.language_repository,
                allowed_language_ids=question_data.allowed_languages,
                template_language_ids=[t.language_id for t in question_data.templates],
            )

            testcase_dtos: list[CreateQuestionTestCaseData] = []
            for index, testcase in enumerate(question_data.testcases):
                testcase_dtos.append(
                    CreateQuestionTestCaseData(
                        input=testcase.input,
                        output=testcase.output,
                        is_hidden=testcase.is_hidden,
                        weight=testcase.weight,
                        order=testcase.order if testcase.order is not None else index,
                    )
                )

            template_dtos: list[CreateQuestionTemplateData] = []
            for template in question_data.templates:
                template_id = uuid.uuid4()
                solution_code_value = template.solution_code
                if solution_code_value:
                    solution_object_key = (
                        self.code_storage_service.build_code_object_key(
                            resource_type="questions",
                            resource_id=question_id,
                            filename=f"templates/{template_id}/solution.txt",
                        )
                    )
                    try:
                        await self.code_storage_service.upload_code(
                            solution_object_key,
                            solution_code_value,
                        )
                    except Exception as error:
                        raise CodeStorageError(
                            f"Failed to upload template solution for language {template.language_id}: {error}"
                        ) from error
                    uploaded_keys.append(solution_object_key)
                    solution_code_value = solution_object_key

                template_dtos.append(
                    CreateQuestionTemplateData(
                        id=template_id,
                        language_id=template.language_id,
                        starter_code=template.starter_code,
                        driver_code=template.driver_code,
                        solution_code=solution_code_value,
                    )
                )

            create_dto = CreateQuestionData(
                id=question_id,
                question_text=question_data.question_text,
                difficulty=question_data.difficulty,
                allowed_language_ids=question_data.allowed_languages,
                testcases=testcase_dtos,
                templates=template_dtos,
                time_limit_ms=question_data.time_limit_ms,
                memory_limit_mb=question_data.memory_limit_mb,
                created_by=user_id,
            )

            question = await self.repository.create_question(create_dto)
            response = QuestionResponse.model_validate(question)
            return response
        except Exception:
            await self.repository.rollback()

            for key in uploaded_keys:
                try:
                    await self.code_storage_service.delete_code(key)
                except Exception:
                    pass

            raise

    @cache_get(
        key_builder=lambda self,
        question_id,
        user_id: f"question:{question_id}:user:{user_id}",
        ttl=300,
    )
    async def get_question_by_id(
        self, question_id: UUID, user_id: UUID
    ) -> QuestionResponse:
        """Retrieve a question by ID for a user.

        Args:
            question_id: Target question ID.
            user_id: Requesting user ID for permission checks.

        Returns:
            Hydrated question response with template code resolved.

        Raises:
            QuestionNotFoundError: If the question does not exist.
            QuestionPermissionError: If user cannot read the question.
            CodeStorageError: If template code hydration fails.
        """
        question = await self.repository.get_question_or_raise(question_id)
        await self.guard.check_read_question(user_id=user_id, question=question)
        response = QuestionResponse.model_validate(question)
        return await self._hydrate_question_template_codes(response)

    @cache_set(
        key_builder=lambda self,
        question_id,
        update_data,
        user_id,
        *args,
        **kwargs: f"question:{question_id}:user:{user_id}",
        ttl=300,
    )
    @cache_delete(
        key_builder=lambda self,
        question_id,
        *args,
        **kwargs: self._get_question_cache_keys(question_id)
    )
    async def update_question(
        self, question_id: UUID, update_data: QuestionUpdate, user_id: UUID
    ) -> QuestionResponse:
        """Update an existing question and reconcile template storage payloads.

        Args:
            question_id: Target question ID.
            update_data: Partial update payload for question aggregate fields.
            user_id: Authenticated user requesting the mutation.

        Returns:
            Updated question response.

        Raises:
            QuestionNotFoundError: If the question does not exist.
            QuestionPermissionError: If user cannot manage the question.
            InvalidQuestionError: If validation fails.
            CodeStorageError: If updated template solution upload fails.
            Exception: Re-raises underlying errors after rollback/cleanup.
        """
        uploaded_keys: list[str] = []
        old_template_keys_to_delete: list[str] = []
        try:
            question = await self.repository.get_question_or_raise(question_id)
            await self.guard.check_manage_question(user_id=user_id, question=question)

            if update_data.testcases is not None:
                self.validator.validate_testcases_format(update_data.testcases)
            self.validator.validate_limits(
                update_data.time_limit_ms, update_data.memory_limit_mb
            )
            if update_data.allowed_languages is not None:
                self.validator.validate_allowed_languages(update_data.allowed_languages)

            await self.validator.validate_platform_languages_exist(
                self.language_repository,
                allowed_language_ids=update_data.allowed_languages or [],
                template_language_ids=[
                    t.language_id for t in (update_data.templates or [])
                ],
            )

            testcase_dtos: list[CreateQuestionTestCaseData] | None = None
            if update_data.testcases is not None:
                testcase_dtos = []
                for index, testcase in enumerate(update_data.testcases):
                    testcase_dtos.append(
                        CreateQuestionTestCaseData(
                            input=testcase.input,
                            output=testcase.output,
                            is_hidden=testcase.is_hidden,
                            weight=testcase.weight,
                            order=testcase.order
                            if testcase.order is not None
                            else index,
                        )
                    )

            template_dtos: list[CreateQuestionTemplateData] | None = None
            if update_data.templates is not None:
                old_template_keys_to_delete = [
                    template.solution_code
                    for template in question.templates
                    if self._is_storage_object_key(template.solution_code)
                ]
                template_dtos = []
                for template in update_data.templates:
                    template_id = uuid.uuid4()
                    solution_code_value = template.solution_code
                    if solution_code_value:
                        solution_object_key = (
                            self.code_storage_service.build_code_object_key(
                                resource_type="questions",
                                resource_id=question.id,
                                filename=f"templates/{template_id}/solution.txt",
                            )
                        )
                        try:
                            await self.code_storage_service.upload_code(
                                solution_object_key,
                                solution_code_value,
                            )
                        except Exception as error:
                            raise CodeStorageError(
                                f"Failed to upload updated template solution for language {template.language_id}: {error}"
                            ) from error
                        uploaded_keys.append(solution_object_key)
                        solution_code_value = solution_object_key

                    template_dtos.append(
                        CreateQuestionTemplateData(
                            id=template_id,
                            language_id=template.language_id,
                            starter_code=template.starter_code,
                            driver_code=template.driver_code,
                            solution_code=solution_code_value,
                        )
                    )

            update_dto = UpdateQuestionData(
                question_text=update_data.question_text,
                difficulty=update_data.difficulty,
                allowed_languages=update_data.allowed_languages,
                testcases=testcase_dtos,
                templates=template_dtos,
                time_limit_ms=update_data.time_limit_ms,
                memory_limit_mb=update_data.memory_limit_mb,
            )

            updated_question = await self.repository.update_question(
                question, update_dto
            )

            for key in old_template_keys_to_delete:
                try:
                    await self.code_storage_service.delete_code(key)
                except Exception:
                    pass

            return QuestionResponse.model_validate(updated_question)
        except Exception:
            await self.repository.rollback()

            for key in uploaded_keys:
                try:
                    await self.code_storage_service.delete_code(key)
                except Exception:
                    pass

            raise

    @cache_delete(
        key_builder=lambda self,
        question_id,
        *args,
        **kwargs: self._get_question_cache_keys(question_id)
    )
    async def delete_question(self, question_id: UUID, user_id: UUID) -> None:
        """Delete a question and invalidate related cache keys.

        Args:
            question_id: Target question ID.
            user_id: Authenticated user requesting deletion.

        Raises:
            QuestionNotFoundError: If the question does not exist.
            QuestionPermissionError: If user cannot manage the question.
        """
        question = await self.repository.get_question_or_raise(question_id)
        await self.guard.check_manage_question(user_id=user_id, question=question)
        await self.repository.delete_question(question)
