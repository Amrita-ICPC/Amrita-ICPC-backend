from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.exceptions.question import QuestionNotFoundError, QuestionPermissionError
from app.models.question import Question


@pytest.mark.asyncio
async def test_get_question_success(
    question_service, mock_repository, mock_guard, sample_question_data
):
    user_id = uuid4()
    question_id = uuid4()
    mock_db_question = Question(
        id=question_id,
        created_by=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        **sample_question_data.model_dump(),
    )

    mock_repository.get_question_or_raise.return_value = mock_db_question
    mock_guard.check_read_question.return_value = None

    result = await question_service.get_question_by_id(question_id, user_id)

    assert result.id == question_id
    mock_repository.get_question_or_raise.assert_called_once_with(question_id)
    mock_guard.check_read_question.assert_called_once_with(
        user_id=user_id, question=mock_db_question
    )


@pytest.mark.asyncio
async def test_get_question_permission_denied(
    question_service, mock_repository, mock_guard, sample_question_data
):
    user_id = uuid4()
    question_id = uuid4()
    mock_db_question = Question(
        id=question_id,
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        **sample_question_data.model_dump(),
    )

    mock_repository.get_question_or_raise.return_value = mock_db_question
    mock_guard.check_read_question.side_effect = QuestionPermissionError()

    with pytest.raises(QuestionPermissionError):
        await question_service.get_question_by_id(question_id, user_id)


@pytest.mark.asyncio
async def test_get_question_not_found(question_service, mock_repository, mock_guard):
    user_id = uuid4()
    question_id = uuid4()

    mock_repository.get_question_or_raise.side_effect = QuestionNotFoundError(
        str(question_id)
    )

    with pytest.raises(QuestionNotFoundError):
        await question_service.get_question_by_id(question_id, user_id)
