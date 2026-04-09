from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.exceptions.bank import (
    BankQuestionAlreadyExistsError,
    BankQuestionNotFoundError,
)
from app.exceptions.bank_validation import BankValidationError
from app.models.bank import Bank, BankQuestion
from app.models.language import Language
from app.models.question import Question, QuestionLanguage
from app.models.question import TestCase as QuestionTestCase
from app.repositories.dto import PaginatedResult
from app.utils.enums import QuestionDifficulty


@pytest.fixture
def mock_repository():
    from app.repositories.bank import BankRepository

    mock = MagicMock(spec=BankRepository)
    mock.db = MagicMock()
    return mock


@pytest.fixture
def mock_validator():
    from app.validators.bank import BankValidator

    return MagicMock(spec=BankValidator)


@pytest.fixture
def mock_question_repo():
    from app.repositories.question import QuestionRepository

    mock = MagicMock(spec=QuestionRepository)
    mock.validate_questions_exist = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def bank_question_service(mock_repository, mock_validator, mock_question_repo):
    with (
        patch(
            "app.core.cache.decorators.cache_get",
            side_effect=lambda **kwargs: lambda func: func,
        ),
        patch(
            "app.core.cache.decorators.cache_set",
            side_effect=lambda **kwargs: lambda func: func,
        ),
        patch(
            "app.core.cache.decorators.cache_delete",
            side_effect=lambda **kwargs: lambda func: func,
        ),
    ):
        from app.service.bank_question_service import BankQuestionService

        mock_storage = MagicMock()
        mock_storage.get_code = AsyncMock(side_effect=lambda value: value)

        return BankQuestionService(
            repository=mock_repository,
            question_repo=mock_question_repo,
            validator=mock_validator,
            code_storage_service=mock_storage,
        )


@pytest.fixture
def sample_bank():
    return Bank(
        id=uuid4(),
        name="Test Bank",
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_deleted=False,
    )


@pytest.fixture
def sample_question():
    question = Question(
        id=uuid4(),
        question_text="Sample Test",
        difficulty=QuestionDifficulty.EASY,
        time_limit_ms=1000,
        memory_limit_mb=256,
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    language = Language(id=71, name="Python 3", slug="python")
    question.languages = [QuestionLanguage(language_id=71, language=language)]
    question.testcases = [
        QuestionTestCase(
            input="1",
            output="1",
            is_hidden=False,
            weight=1,
            order=0,
            created_by=question.created_by,
        )
    ]
    question.templates = []
    return question


@pytest.mark.asyncio
async def test_add_question_to_bank_success(
    bank_question_service,
    mock_repository,
    mock_validator,
    sample_bank,
    mock_question_repo,
):
    user_id = sample_bank.created_by
    question_id = uuid4()

    mock_repository.get_bank_or_raise.return_value = sample_bank
    mock_repository.get_questions_in_bank_by_ids.return_value = []

    mock_question_repo.validate_questions_exist = AsyncMock(return_value=None)

    await bank_question_service.add_questions_to_bank(
        sample_bank.id, [question_id], user_id
    )

    mock_question_repo.validate_questions_exist.assert_awaited_once_with([question_id])

    mock_repository.add_questions_to_bank.assert_called_once_with(
        sample_bank.id, [question_id], user_id
    )


@pytest.mark.asyncio
async def test_add_question_to_bank_already_exists(
    bank_question_service,
    mock_repository,
    mock_validator,
    sample_bank,
    mock_question_repo,
):
    user_id = sample_bank.created_by
    question_id = uuid4()

    mock_repository.get_bank_or_raise.return_value = sample_bank
    mock_repository.get_questions_in_bank_by_ids.return_value = [
        BankQuestion(bank_id=sample_bank.id, question_id=question_id)
    ]

    mock_question_repo.validate_questions_exist = AsyncMock(return_value=None)

    with pytest.raises(BankQuestionAlreadyExistsError):
        await bank_question_service.add_questions_to_bank(
            sample_bank.id, [question_id], user_id
        )

    mock_question_repo.validate_questions_exist.assert_awaited_once_with([question_id])


@pytest.mark.asyncio
async def test_add_questions_to_bank_rejects_duplicate_question_ids(
    bank_question_service,
    mock_repository,
    mock_validator,
    sample_bank,
    mock_question_repo,
):
    user_id = sample_bank.created_by
    question_id = uuid4()
    duplicate_payload = [question_id, question_id]

    mock_repository.get_bank_or_raise.return_value = sample_bank

    with pytest.raises(BankValidationError):
        await bank_question_service.add_questions_to_bank(
            sample_bank.id, duplicate_payload, user_id
        )

    mock_question_repo.validate_questions_exist.assert_not_called()
    mock_repository.get_questions_in_bank_by_ids.assert_not_called()
    mock_repository.add_questions_to_bank.assert_not_called()


@pytest.mark.asyncio
async def test_remove_question_from_bank_success(
    bank_question_service, mock_repository, mock_validator, sample_bank
):
    user_id = sample_bank.created_by
    question_id = uuid4()

    mock_bq = BankQuestion(bank_id=sample_bank.id, question_id=question_id)
    mock_repository.get_bank_or_raise.return_value = sample_bank
    mock_repository.get_questions_in_bank_by_ids.return_value = [mock_bq]
    await bank_question_service.remove_questions_from_bank(
        sample_bank.id, [question_id], user_id
    )
    mock_repository.remove_questions_from_bank.assert_called_once_with([mock_bq])


@pytest.mark.asyncio
async def test_remove_question_from_bank_not_found(
    bank_question_service, mock_repository, mock_validator, sample_bank
):
    user_id = sample_bank.created_by
    question_id = uuid4()

    mock_repository.get_bank_or_raise.return_value = sample_bank
    mock_repository.get_questions_in_bank_by_ids.return_value = []

    with pytest.raises(BankQuestionNotFoundError):
        await bank_question_service.remove_questions_from_bank(
            sample_bank.id, [question_id], user_id
        )


@pytest.mark.asyncio
async def test_get_bank_questions_success(
    bank_question_service, mock_repository, mock_validator, sample_bank, sample_question
):
    user_id = sample_bank.created_by

    mock_repository.get_bank_or_raise.return_value = sample_bank

    result = PaginatedResult(total=1, items=[sample_question])
    mock_repository.get_questions_in_bank.return_value = result
    total, questions = await bank_question_service.get_bank_questions(
        sample_bank.id, user_id, 0, 10
    )
    assert total == 1
    assert len(questions) == 1
    assert questions[0].id == sample_question.id
    assert questions[0].testcase_count == 1


@pytest.mark.asyncio
async def test_clone_selected_questions_between_banks_success(
    bank_question_service,
    mock_repository,
    sample_bank,
    sample_question,
):
    user_id = sample_bank.created_by
    source_bank_id = sample_bank.id
    target_bank_id = uuid4()

    target_bank = Bank(
        id=target_bank_id,
        name="Target Bank",
        created_by=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_deleted=False,
    )

    mock_repository.get_bank_or_raise.side_effect = [sample_bank, target_bank]
    mock_repository.get_questions_in_bank_by_ids.return_value = [
        BankQuestion(bank_id=source_bank_id, question_id=sample_question.id)
    ]
    mock_repository.get_question_entities_in_bank_by_ids.return_value = [
        sample_question
    ]
    bank_question_service.question_repo.bulk_create_questions = AsyncMock(
        side_effect=lambda questions: questions
    )

    cloned_count = await bank_question_service.clone_questions_between_banks(
        source_bank_id,
        target_bank_id,
        user_id,
        copy_all=False,
        question_ids=[sample_question.id],
    )

    assert cloned_count == 1
    bank_question_service.question_repo.bulk_create_questions.assert_awaited_once()
    add_call = mock_repository.add_questions_to_bank.call_args
    assert add_call.args[0] == target_bank_id
    assert len(add_call.args[1]) == 1
    assert add_call.args[1][0] != sample_question.id
    assert add_call.args[2] == user_id


@pytest.mark.asyncio
async def test_clone_all_questions_between_banks_success(
    bank_question_service,
    mock_repository,
    sample_bank,
    sample_question,
):
    user_id = sample_bank.created_by
    source_bank_id = sample_bank.id
    target_bank_id = uuid4()

    target_bank = Bank(
        id=target_bank_id,
        name="Target Bank",
        created_by=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_deleted=False,
    )

    mock_repository.get_bank_or_raise.side_effect = [sample_bank, target_bank]
    mock_repository.get_all_question_entities_in_bank.return_value = [sample_question]
    bank_question_service.question_repo.bulk_create_questions = AsyncMock(
        side_effect=lambda questions: questions
    )

    cloned_count = await bank_question_service.clone_questions_between_banks(
        source_bank_id,
        target_bank_id,
        user_id,
        copy_all=True,
        question_ids=None,
    )

    assert cloned_count == 1
    mock_repository.get_questions_in_bank_by_ids.assert_not_called()
    bank_question_service.question_repo.bulk_create_questions.assert_awaited_once()


@pytest.mark.asyncio
async def test_clone_selected_questions_raises_when_not_in_source_bank(
    bank_question_service,
    mock_repository,
    sample_bank,
):
    user_id = sample_bank.created_by
    source_bank_id = sample_bank.id
    target_bank_id = uuid4()
    target_bank = Bank(
        id=target_bank_id,
        name="Target Bank",
        created_by=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_deleted=False,
    )
    selected_question_id = uuid4()

    mock_repository.get_bank_or_raise.side_effect = [sample_bank, target_bank]
    mock_repository.get_questions_in_bank_by_ids.return_value = []

    with pytest.raises(BankQuestionNotFoundError):
        await bank_question_service.clone_questions_between_banks(
            source_bank_id,
            target_bank_id,
            user_id,
            copy_all=False,
            question_ids=[selected_question_id],
        )
