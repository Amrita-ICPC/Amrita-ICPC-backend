from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.question import Question, Submission
from worker.evaluation import _evaluate_submission_async, evaluate_submission


@pytest.mark.asyncio
@patch("worker.evaluation.SessionLocal")
@patch("worker.evaluation.QuestionRepository")
async def test_evaluate_submission_async_success(
    mock_question_repo_cls: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    submission_id = uuid4()
    question_id = uuid4()

    # Mock DB Session
    mock_db = AsyncMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    # Mock repository
    mock_repo = AsyncMock()
    mock_question_repo_cls.return_value = mock_repo

    # Mock submission query result
    mock_submission = MagicMock(spec=Submission)
    mock_submission.id = submission_id
    mock_submission.question_id = question_id
    mock_repo.get_submission.return_value = mock_submission

    # Mock question and testcases
    mock_question = MagicMock(spec=Question)
    mock_question.title = "Test Question"
    mock_testcase1 = MagicMock()
    mock_testcase1.id = uuid4()
    mock_testcase1.input = "input1"
    mock_testcase1.output = "output1"
    mock_testcase1.is_hidden = False

    mock_question.testcases = [mock_testcase1]
    mock_repo.get_question_or_raise.return_value = mock_question

    # Run the helper
    await _evaluate_submission_async(submission_id)

    # Asserts
    mock_session_local.assert_called_once()
    mock_repo.get_submission.assert_called_once_with(submission_id)
    mock_repo.get_question_or_raise.assert_called_once_with(question_id)


@pytest.mark.asyncio
@patch("worker.evaluation.SessionLocal")
@patch("worker.evaluation.QuestionRepository")
async def test_evaluate_submission_async_not_found(
    mock_question_repo_cls: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    submission_id = uuid4()

    mock_db = AsyncMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    mock_repo = AsyncMock()
    mock_question_repo_cls.return_value = mock_repo
    mock_repo.get_submission.return_value = None

    # Run helper
    await _evaluate_submission_async(submission_id)

    # Asserts
    mock_repo.get_submission.assert_called_once_with(submission_id)


@patch("worker.evaluation.asyncio.run")
@patch("worker.evaluation._evaluate_submission_async")
def test_evaluate_submission_task_calls(
    mock_helper: MagicMock, mock_run: MagicMock
) -> None:
    submission_id = uuid4()

    evaluate_submission(submission_id)

    mock_run.assert_called_once()


@patch("worker.evaluation.asyncio.run")
@patch("worker.evaluation._evaluate_submission_async")
def test_evaluate_submission_task_string_id(
    mock_helper: MagicMock, mock_run: MagicMock
) -> None:
    submission_id_str = "4f8c14db-99e5-4e78-9a99-b1d50c763ab3"

    evaluate_submission(submission_id_str)

    mock_run.assert_called_once()
    mock_helper.assert_called_once_with(UUID(submission_id_str))
