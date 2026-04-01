from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.exceptions.bank import (
    BankQuestionAlreadyExistsError,
    BankQuestionNotFoundError,
)
from app.models.bank import Bank, BankQuestion
from app.models.question import Question
from app.repositories.dto import PaginatedResult


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
    mock.get_question_or_raise = AsyncMock(return_value=MagicMock())
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

        return BankQuestionService(
            repository=mock_repository,
            question_repo=mock_question_repo,
            validator=mock_validator,
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
    from app.utils.enums import QuestionDifficulty

    return Question(
        id=uuid4(),
        question_text="Sample Test",
        difficulty=QuestionDifficulty.EASY,
        allowed_languages=["python"],
        testcases=[{"input": "1", "output": "1", "is_hidden": False}],
        time_limit_ms=1000,
        memory_limit_mb=256,
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


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

    mock_question_repo.get_question_or_raise = AsyncMock(return_value=MagicMock())

    await bank_question_service.add_questions_to_bank(
        sample_bank.id, [question_id], user_id
    )

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

    mock_question_repo.get_question_or_raise = AsyncMock(return_value=MagicMock())

    with pytest.raises(BankQuestionAlreadyExistsError):
        await bank_question_service.add_questions_to_bank(
            sample_bank.id, [question_id], user_id
        )


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
