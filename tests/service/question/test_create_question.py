from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.exceptions.question import InvalidQuestionError
from app.models.question import Question


@pytest.mark.asyncio
async def test_create_question_success(
    question_service, mock_repository, mock_validator, sample_question_data
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
    mock_repository.create_question.return_value = mock_db_question

    result = await question_service.create_question(sample_question_data, user_id)

    assert result.id == question_id
    assert result.question_text == sample_question_data.question_text
    mock_repository.create_question.assert_called_once()
    mock_validator.validate_testcases_format.assert_called_once_with(
        sample_question_data.testcases
    )
    mock_validator.validate_limits.assert_called_once_with(
        sample_question_data.time_limit_ms, sample_question_data.memory_limit_mb
    )


@pytest.mark.asyncio
async def test_create_question_invalid_testcases(
    question_service, mock_repository, mock_validator, sample_question_data
):
    user_id = uuid4()
    mock_validator.validate_testcases_format.side_effect = InvalidQuestionError(
        "Invalid"
    )

    with pytest.raises(InvalidQuestionError):
        await question_service.create_question(sample_question_data, user_id)

    mock_repository.create_question.assert_not_called()
