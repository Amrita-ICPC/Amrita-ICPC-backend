import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.evaluation import Evaluation
from app.models.question import Question, Submission
from app.repositories.dto.evaluation import EvaluationResult
from app.utils.enums import SubmissionStatus
from worker.evaluation import (
    _evaluate_submission_async,
    _update_progress_db_and_redis,
    evaluate_contest_submission,
    evaluate_submission,
)


@pytest.mark.asyncio
@patch("worker.evaluation.SessionLocal")
@patch("worker.evaluation.QuestionRepository")
@patch("worker.evaluation._run_evaluation")
async def test_evaluate_submission_async_success(
    mock_run_evaluation: MagicMock,
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
    mock_submission.is_evaluated = False
    mock_submission.contest_submission = None
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

    # Mock evaluation result
    mock_run_evaluation.return_value = EvaluationResult(
        status=SubmissionStatus.AC,
        passed_testcases=1,
        total_testcases=1,
        total_time=100,
        total_memory=1024,
        testcase_results=[],
    )

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


@patch("worker.evaluation.asyncio")
@patch("worker.evaluation._evaluate_submission_async")
def test_evaluate_submission_task_calls(
    mock_helper: MagicMock, mock_asyncio: MagicMock
) -> None:
    submission_id = uuid4()

    mock_loop = MagicMock()
    mock_asyncio.get_event_loop.return_value = mock_loop

    evaluate_submission(submission_id)

    mock_loop.run_until_complete.assert_called_once()


@patch("worker.evaluation.asyncio")
@patch("worker.evaluation._evaluate_submission_async")
def test_evaluate_submission_task_string_id(
    mock_helper: MagicMock, mock_asyncio: MagicMock
) -> None:
    submission_id_str = "4f8c14db-99e5-4e78-9a99-b1d50c763ab3"

    mock_loop = MagicMock()
    mock_asyncio.get_event_loop.return_value = mock_loop

    evaluate_submission(submission_id_str)

    mock_loop.run_until_complete.assert_called_once()
    mock_helper.assert_called_once_with(UUID(submission_id_str))


@pytest.mark.asyncio
@patch("worker.evaluation.SessionLocal")
@patch("worker.evaluation.get_redis")
async def test_update_progress_async_success(
    mock_get_redis: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    evaluation_id = uuid4()

    # Mock DB Session
    mock_db = AsyncMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    # Mock evaluation model
    mock_eval = MagicMock(spec=Evaluation)
    mock_eval.id = evaluation_id
    mock_eval.processed_submissions = 1
    mock_eval.total_submissions = 3
    mock_eval.is_evaluated = False

    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = mock_eval
    mock_db.execute.return_value = mock_db_result

    # Mock Redis
    mock_redis_client = MagicMock()
    mock_lock = AsyncMock()
    mock_redis_client.lock.return_value = mock_lock
    mock_redis_client.get = AsyncMock(
        return_value=json.dumps({"processed": 1, "total": 3, "status": "RUNNING"})
    )
    mock_redis_client.set = AsyncMock()
    mock_get_redis.return_value = mock_redis_client

    # Run first increment
    await _update_progress_db_and_redis(evaluation_id)

    # Asserts
    assert mock_eval.processed_submissions == 2
    assert mock_eval.is_evaluated is False
    mock_db.commit.assert_called_once()
    mock_redis_client.set.assert_called_once()

    # Reset mock and run to completion
    mock_db.commit.reset_mock()
    mock_redis_client.set.reset_mock()
    await _update_progress_db_and_redis(evaluation_id)
    assert mock_eval.is_evaluated is True
    assert mock_eval.processed_submissions == 3
    mock_db.commit.assert_called_once()
    mock_redis_client.set.assert_called_once()


@patch("worker.evaluation.asyncio")
@patch("worker.evaluation._evaluate_contest_submission_async")
def test_evaluate_contest_submission_task_calls(
    mock_evaluate_contest_sub: MagicMock,
    mock_asyncio: MagicMock,
) -> None:
    evaluation_id = uuid4()
    submission_id = uuid4()

    mock_loop = MagicMock()
    mock_asyncio.get_event_loop.return_value = mock_loop

    evaluate_contest_submission(evaluation_id, submission_id)

    mock_loop.run_until_complete.assert_called_once()
    mock_evaluate_contest_sub.assert_called_once_with(evaluation_id, submission_id)


@pytest.mark.asyncio
@patch("worker.evaluation.SessionLocal")
@patch("worker.evaluation.QuestionRepository")
@patch("worker.evaluation._evaluate_submission_core")
async def test_evaluate_contest_submission_async_superseded(
    mock_evaluate_core: MagicMock,
    mock_question_repo_cls: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    evaluation_id = uuid4()
    submission_id = uuid4()

    # Mock DB Session
    mock_db = AsyncMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    # Mock Evaluation.is_evaluated is True in database (already superseded)
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = True
    mock_db.execute.return_value = mock_execute_result

    # Run helper
    from worker.evaluation import _evaluate_contest_submission_async

    await _evaluate_contest_submission_async(evaluation_id, submission_id)

    # Asserts
    # Should check database for evaluation status
    mock_db.execute.assert_called_once()
    # Should return early without calling repository get_submission or evaluate_core
    mock_question_repo_cls.assert_not_called()
    mock_evaluate_core.assert_not_called()
