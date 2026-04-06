from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.schema.question import (
    QuestionCreate,
    QuestionTemplateCreate,
    QuestionTestCaseCreate,
    QuestionUpdate,
)
from app.utils.enums import QuestionDifficulty


def _build_question_entity(
    *,
    question_id: UUID,
    created_by: UUID,
    question_text: str,
    difficulty: QuestionDifficulty,
    allowed_language_ids: list[int],
    time_limit_ms: int,
    memory_limit_mb: int,
    testcases: list[SimpleNamespace],
    templates: list[SimpleNamespace],
):
    return SimpleNamespace(
        id=question_id,
        question_text=question_text,
        difficulty=difficulty,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        languages=[
            SimpleNamespace(language_id=language_id)
            for language_id in allowed_language_ids
        ],
        testcases=testcases,
        templates=templates,
    )


@pytest.fixture
def mock_repository():
    from app.repositories.question import QuestionRepository

    mock = MagicMock(spec=QuestionRepository)
    mock.create_question = AsyncMock()
    mock.get_question_or_raise = AsyncMock()
    mock.update_question = AsyncMock()
    mock.rollback = AsyncMock()
    return mock


@pytest.fixture
def mock_language_repository():
    from app.repositories.language import LanguageRepository

    return MagicMock(spec=LanguageRepository)


@pytest.fixture
def mock_guard():
    from app.core.guards.question import QuestionOperationGuard

    guard = MagicMock(spec=QuestionOperationGuard)
    guard.check_manage_question = AsyncMock(return_value=None)
    return guard


@pytest.fixture
def mock_validator():
    from app.validators.question import QuestionValidator

    validator = MagicMock(spec=QuestionValidator)
    validator.validate_testcases_format = MagicMock(return_value=None)
    validator.validate_limits = MagicMock(return_value=None)
    validator.validate_allowed_languages = MagicMock(return_value=None)
    validator.validate_platform_languages_exist = AsyncMock(return_value=None)
    return validator


@pytest.fixture
def mock_code_storage_service():
    from app.core.storage import CodeStorageService

    storage = MagicMock(spec=CodeStorageService)
    storage.build_code_object_key = MagicMock(
        side_effect=lambda resource_type,
        resource_id,
        filename: f"code/{resource_type}/{resource_id}/{filename}"
    )
    storage.upload_code = AsyncMock(return_value=None)
    storage.delete_code = AsyncMock(return_value=None)
    return storage


@pytest.fixture
def question_service(
    mock_repository,
    mock_language_repository,
    mock_guard,
    mock_validator,
    mock_code_storage_service,
):
    with (
        patch("app.core.cache.decorators.cache_get", lambda **kw: lambda f: f),
        patch("app.core.cache.decorators.cache_set", lambda **kw: lambda f: f),
        patch("app.core.cache.decorators.cache_delete", lambda **kw: lambda f: f),
    ):
        from app.service.question_service import QuestionService

        return QuestionService(
            repository=mock_repository,
            language_repository=mock_language_repository,
            guard=mock_guard,
            validator=mock_validator,
            code_storage_service=mock_code_storage_service,
        )


@pytest.mark.asyncio
async def test_create_question_success_uploads_solution_code(
    question_service,
    mock_repository,
    mock_validator,
    mock_code_storage_service,
):
    user_id = uuid4()
    create_data = QuestionCreate(
        question_text="Two Sum",
        difficulty=QuestionDifficulty.EASY,
        allowed_languages=[71],
        time_limit_ms=1000,
        memory_limit_mb=256,
        testcases=[
            QuestionTestCaseCreate(
                input="2\n1 2\n3",
                output="1 2",
                is_hidden=False,
                weight=1,
                order=0,
            )
        ],
        templates=[
            QuestionTemplateCreate(
                language_id=71,
                starter_code="def solve():\n    pass",
                driver_code=None,
                solution_code="print('ok')",
            )
        ],
    )

    async def _create_side_effect(dto):
        return _build_question_entity(
            question_id=dto.id,
            created_by=user_id,
            question_text=dto.question_text,
            difficulty=dto.difficulty,
            allowed_language_ids=dto.allowed_language_ids,
            time_limit_ms=dto.time_limit_ms,
            memory_limit_mb=dto.memory_limit_mb,
            testcases=[
                SimpleNamespace(
                    input=t.input,
                    output=t.output,
                    is_hidden=t.is_hidden,
                    weight=t.weight,
                    order=t.order,
                )
                for t in dto.testcases
            ],
            templates=[
                SimpleNamespace(
                    language_id=t.language_id,
                    starter_code=t.starter_code,
                    driver_code=t.driver_code,
                    solution_code=t.solution_code,
                )
                for t in dto.templates
            ],
        )

    mock_repository.create_question.side_effect = _create_side_effect

    response = await question_service.create_question(create_data, user_id)

    assert response.question_text == "Two Sum"
    assert response.allowed_languages == [71]
    assert len(response.templates) == 1
    assert response.templates[0].solution_code is not None
    assert response.templates[0].solution_code.startswith("code/questions/")

    mock_code_storage_service.upload_code.assert_awaited_once()
    mock_repository.rollback.assert_not_awaited()
    mock_validator.validate_platform_languages_exist.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_question_failure_rolls_back_and_deletes_uploaded_objects(
    question_service,
    mock_repository,
    mock_code_storage_service,
):
    user_id = uuid4()
    create_data = QuestionCreate(
        question_text="Two Sum",
        difficulty=QuestionDifficulty.EASY,
        allowed_languages=[71],
        time_limit_ms=1000,
        memory_limit_mb=256,
        testcases=[
            QuestionTestCaseCreate(
                input="2\n1 2\n3",
                output="1 2",
                is_hidden=False,
                weight=1,
                order=0,
            )
        ],
        templates=[
            QuestionTemplateCreate(
                language_id=71,
                starter_code="def solve():\n    pass",
                driver_code=None,
                solution_code="print('ok')",
            )
        ],
    )

    mock_repository.create_question.side_effect = RuntimeError("db write failed")

    with pytest.raises(RuntimeError, match="db write failed"):
        await question_service.create_question(create_data, user_id)

    mock_repository.rollback.assert_awaited_once()
    mock_code_storage_service.upload_code.assert_awaited_once()

    uploaded_key = mock_code_storage_service.upload_code.await_args.args[0]
    mock_code_storage_service.delete_code.assert_awaited_once_with(uploaded_key)


@pytest.mark.asyncio
async def test_update_question_updates_relations_and_replaces_template_code(
    question_service,
    mock_repository,
    mock_guard,
    mock_validator,
    mock_code_storage_service,
):
    user_id = uuid4()
    question_id = uuid4()

    existing_question = _build_question_entity(
        question_id=question_id,
        created_by=user_id,
        question_text="Old",
        difficulty=QuestionDifficulty.EASY,
        allowed_language_ids=[71],
        time_limit_ms=1000,
        memory_limit_mb=256,
        testcases=[
            SimpleNamespace(
                input="1",
                output="1",
                is_hidden=False,
                weight=1,
                order=0,
            )
        ],
        templates=[
            SimpleNamespace(
                language_id=71,
                starter_code="old starter",
                driver_code=None,
                solution_code="code/questions/old/template/solution.txt",
            )
        ],
    )

    update_data = QuestionUpdate(
        question_text="New",
        difficulty=QuestionDifficulty.MEDIUM,
        allowed_languages=[71, 62],
        time_limit_ms=2000,
        memory_limit_mb=512,
        testcases=[
            QuestionTestCaseCreate(
                input="3\n1 2 3",
                output="6",
                is_hidden=False,
                weight=1,
                order=0,
            )
        ],
        templates=[
            QuestionTemplateCreate(
                language_id=62,
                starter_code="class Main {}",
                driver_code=None,
                solution_code="System.out.println(1);",
            )
        ],
    )

    mock_repository.get_question_or_raise.return_value = existing_question

    async def _update_side_effect(question, dto):
        return _build_question_entity(
            question_id=question.id,
            created_by=question.created_by,
            question_text=dto.question_text or question.question_text,
            difficulty=dto.difficulty or question.difficulty,
            allowed_language_ids=dto.allowed_languages or [71],
            time_limit_ms=dto.time_limit_ms or question.time_limit_ms,
            memory_limit_mb=dto.memory_limit_mb or question.memory_limit_mb,
            testcases=[
                SimpleNamespace(
                    input=t.input,
                    output=t.output,
                    is_hidden=t.is_hidden,
                    weight=t.weight,
                    order=t.order,
                )
                for t in (dto.testcases or [])
            ],
            templates=[
                SimpleNamespace(
                    language_id=t.language_id,
                    starter_code=t.starter_code,
                    driver_code=t.driver_code,
                    solution_code=t.solution_code,
                )
                for t in (dto.templates or [])
            ],
        )

    mock_repository.update_question.side_effect = _update_side_effect

    response = await question_service.update_question(question_id, update_data, user_id)

    assert response.question_text == "New"
    assert response.allowed_languages == [71, 62]
    assert len(response.templates) == 1
    assert response.templates[0].language_id == 62
    assert response.templates[0].solution_code is not None
    assert response.templates[0].solution_code.startswith("code/questions/")

    mock_guard.check_manage_question.assert_awaited_once_with(
        user_id=user_id,
        question=existing_question,
    )
    mock_validator.validate_platform_languages_exist.assert_awaited_once_with(
        question_service.language_repository,
        allowed_language_ids=[71, 62],
        template_language_ids=[62],
    )
    mock_code_storage_service.upload_code.assert_awaited_once()
    old_key = "code/questions/old/template/solution.txt"
    mock_code_storage_service.delete_code.assert_any_await(old_key)
    mock_repository.rollback.assert_not_awaited()

    update_call_args = mock_repository.update_question.await_args.args
    update_dto = update_call_args[1]
    assert update_dto.allowed_languages == [71, 62]
    assert update_dto.testcases is not None
    assert update_dto.templates is not None
    assert update_dto.templates[0].solution_code is not None
    assert update_dto.templates[0].solution_code.startswith("code/questions/")
