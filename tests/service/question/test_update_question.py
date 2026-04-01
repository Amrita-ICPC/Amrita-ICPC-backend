from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.exceptions.question import QuestionPermissionError
from app.models.question import Question
from app.schema.question import QuestionUpdate


@pytest.mark.asyncio
async def test_update_question_success(
    question_service, mock_repository, mock_guard, mock_validator, sample_question_data
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

    update_data = QuestionUpdate(question_text="New text", time_limit_ms=2000)

    updated_db_question = Question(
        id=question_id,
        created_by=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        **sample_question_data.model_dump(),
    )
    updated_db_question.question_text = "New text"
    updated_db_question.time_limit_ms = 2000

    mock_repository.get_question_or_raise.return_value = mock_db_question
    mock_repository.update_question.return_value = updated_db_question

    result = await question_service.update_question(question_id, update_data, user_id)

    assert result.question_text == "New text"
    assert result.time_limit_ms == 2000
    mock_repository.update_question.assert_called_once()
    mock_guard.check_manage_question.assert_called_once_with(
        user_id=user_id, question=mock_db_question
    )


@pytest.mark.asyncio
async def test_update_question_permission_denied(
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

    update_data = QuestionUpdate(question_text="New text")

    mock_repository.get_question_or_raise.return_value = mock_db_question
    mock_guard.check_manage_question.side_effect = QuestionPermissionError()

    with pytest.raises(QuestionPermissionError):
        await question_service.update_question(question_id, update_data, user_id)
