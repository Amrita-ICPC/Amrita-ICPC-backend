import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.question import Question, Submission
from app.repositories.dto.evaluation import EvaluationResult
from app.utils.enums import SubmissionStatus
from worker.evaluation import (
    _evaluate_submission_async,
    _update_progress_redis,
    evaluate_contest_submission,
    evaluate_submission,
)


@pytest.mark.asyncio
@patch("worker.evaluation.SessionLocal")
@patch("worker.evaluation.QuestionRepository")
@patch("worker.evaluation._run_evaluation")
@patch("worker.evaluation.QuestionValidator")
async def test_evaluate_submission_async_success(
    mock_validator: MagicMock,
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

    # Mock QuestionValidator
    mock_validator.validate_submission_language.return_value = MagicMock()

    # Mock question and testcases
    mock_question = MagicMock(spec=Question)
    mock_question.title = "Test Question"
    mock_testcase1 = MagicMock()
    mock_testcase1.id = uuid4()
    mock_testcase1.input = "input1"
    mock_testcase1.output = "output1"
    mock_testcase1.is_hidden = False
    mock_testcase1.weight = 1

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
    assert mock_session_local.call_count == 2
    assert mock_repo.get_submission.call_count == 2
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
@patch("worker.evaluation.get_redis")
async def test_update_progress_redis_success(
    mock_get_redis: MagicMock,
) -> None:
    contest_id = uuid4()
    evaluation_id = uuid4()

    # Mock Redis
    mock_redis_client = MagicMock()
    mock_lock = AsyncMock()
    mock_redis_client.lock.return_value = mock_lock

    redis_data = {
        "id": str(evaluation_id),
        "contest_id": str(contest_id),
        "is_evaluated": False,
        "total_submissions": 3,
        "processed_submissions": 1,
        "status": "RUNNING",
    }

    mock_redis_client.get = AsyncMock(return_value=json.dumps(redis_data))
    mock_redis_client.set = AsyncMock()
    mock_get_redis.return_value = mock_redis_client

    # Run first increment
    await _update_progress_redis(contest_id, evaluation_id)

    # Asserts
    mock_redis_client.set.assert_called_once()
    called_key, called_val = mock_redis_client.set.call_args[0]
    assert called_key == f"contests:{contest_id}:evaluation"
    called_data = json.loads(called_val)
    assert called_data["processed_submissions"] == 2
    assert called_data["status"] == "RUNNING"
    assert called_data.get("is_evaluated") is not True

    # Reset mock and run to completion
    mock_redis_client.set.reset_mock()

    # Update the get mock to return the updated data
    redis_data["processed_submissions"] = 2
    mock_redis_client.get.return_value = json.dumps(redis_data)

    await _update_progress_redis(contest_id, evaluation_id)
    called_key, called_val = mock_redis_client.set.call_args[0]
    called_data = json.loads(called_val)
    assert called_data["processed_submissions"] == 3
    assert called_data["status"] == "COMPLETED"
    assert called_data["is_evaluated"] is True


@patch("worker.evaluation.asyncio")
@patch("worker.evaluation._evaluate_contest_submission_async")
def test_evaluate_contest_submission_task_calls(
    mock_evaluate_contest_sub: MagicMock,
    mock_asyncio: MagicMock,
) -> None:
    contest_id = uuid4()
    evaluation_id = uuid4()
    submission_id = uuid4()

    mock_loop = MagicMock()
    mock_asyncio.get_event_loop.return_value = mock_loop

    evaluate_contest_submission(contest_id, evaluation_id, submission_id)

    mock_loop.run_until_complete.assert_called_once()
    mock_evaluate_contest_sub.assert_called_once_with(
        contest_id, evaluation_id, submission_id
    )


@pytest.mark.asyncio
@patch("worker.evaluation.SessionLocal")
@patch("worker.evaluation.QuestionRepository")
@patch("worker.evaluation._run_evaluation")
@patch("worker.evaluation.get_redis")
async def test_evaluate_contest_submission_async_superseded(
    mock_get_redis: MagicMock,
    mock_run_evaluation: MagicMock,
    mock_question_repo_cls: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    contest_id = uuid4()
    evaluation_id = uuid4()
    submission_id = uuid4()

    # Mock DB Session
    mock_db = AsyncMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    # Mock Redis return value to represent a superseded evaluation
    mock_redis_client = MagicMock()
    mock_redis_client.get = AsyncMock(
        return_value=json.dumps({"id": str(uuid4()), "status": "RUNNING"})
    )
    mock_get_redis.return_value = mock_redis_client

    # Run helper
    from worker.evaluation import _evaluate_contest_submission_async

    await _evaluate_contest_submission_async(contest_id, evaluation_id, submission_id)

    # Asserts
    # Should check Redis
    mock_redis_client.get.assert_called_once_with(f"contests:{contest_id}:evaluation")
    # Should return early without calling repository get_submission or run_evaluation
    mock_question_repo_cls.assert_not_called()
    mock_run_evaluation.assert_not_called()


@pytest.mark.asyncio
@patch("worker.evaluation.SessionLocal")
@patch("worker.evaluation.QuestionRepository")
@patch("worker.evaluation._run_evaluation")
@patch("worker.evaluation.QuestionValidator")
@patch("worker.evaluation._update_progress_redis")
@patch("worker.evaluation.get_redis")
async def test_evaluate_contest_submission_async_with_existing_testcases(
    mock_get_redis: MagicMock,
    mock_update_progress: MagicMock,
    mock_validator: MagicMock,
    mock_run_evaluation: MagicMock,
    mock_question_repo_cls: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    contest_id = uuid4()
    evaluation_id = uuid4()
    submission_id = uuid4()

    # Mock DB Session
    mock_db = AsyncMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    # Setup database execute mock
    mock_res_stc = MagicMock()
    mock_res_stc.scalar_one_or_none.return_value = uuid4()  # dummy testcase id
    mock_db.execute.return_value = mock_res_stc

    # Mock Redis
    mock_redis_client = MagicMock()
    mock_redis_client.get = AsyncMock(
        return_value=json.dumps({"id": str(evaluation_id), "status": "RUNNING"})
    )
    mock_get_redis.return_value = mock_redis_client

    # Mock Repository and Submission
    mock_repo = AsyncMock()
    mock_question_repo_cls.return_value = mock_repo

    mock_submission = MagicMock(spec=Submission)
    mock_submission.id = submission_id
    mock_submission.is_evaluated = False
    mock_submission.status = SubmissionStatus.AC
    mock_submission.contest_submission = None
    mock_repo.get_submission.return_value = mock_submission

    # Mock QuestionValidator
    mock_validator.validate_submission_language.return_value = MagicMock()

    # Mock Question
    mock_question = MagicMock(spec=Question)
    mock_question.title = "Test Question"
    mock_testcase1 = MagicMock()
    mock_testcase1.id = uuid4()
    mock_testcase1.input = "input1"
    mock_testcase1.output = "output1"
    mock_testcase1.is_hidden = False
    mock_testcase1.weight = 1
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

    # Run
    from worker.evaluation import _evaluate_contest_submission_async

    await _evaluate_contest_submission_async(contest_id, evaluation_id, submission_id)

    # Asserts
    # delete_submission_testcases_batch should be called on the repository
    mock_repo.delete_submission_testcases_batch.assert_called_once_with(submission_id)
    # should run evaluation
    mock_run_evaluation.assert_called_once()
    # should update progress
    mock_update_progress.assert_called_once_with(contest_id, evaluation_id)


@pytest.mark.asyncio
@patch("worker.evaluation.SessionLocal")
@patch("worker.evaluation.QuestionRepository")
@patch("worker.evaluation._run_evaluation")
@patch("worker.evaluation.QuestionValidator")
@patch("worker.evaluation._update_progress_redis")
@patch("worker.evaluation.get_redis")
async def test_evaluate_contest_submission_async_no_existing_testcases(
    mock_get_redis: MagicMock,
    mock_update_progress: MagicMock,
    mock_validator: MagicMock,
    mock_run_evaluation: MagicMock,
    mock_question_repo_cls: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    contest_id = uuid4()
    evaluation_id = uuid4()
    submission_id = uuid4()

    # Mock DB Session
    mock_db = AsyncMock()
    mock_session_local.return_value.__aenter__.return_value = mock_db

    # Setup database execute mock: testcases do not exist
    mock_res_stc = MagicMock()
    mock_res_stc.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res_stc

    # Mock Redis
    mock_redis_client = MagicMock()
    mock_redis_client.get = AsyncMock(
        return_value=json.dumps({"id": str(evaluation_id), "status": "RUNNING"})
    )
    mock_get_redis.return_value = mock_redis_client

    # Mock Repository and Submission
    mock_repo = AsyncMock()
    mock_question_repo_cls.return_value = mock_repo

    mock_submission = MagicMock(spec=Submission)
    mock_submission.id = submission_id
    mock_submission.is_evaluated = False
    mock_submission.status = SubmissionStatus.AC
    mock_submission.contest_submission = None
    mock_repo.get_submission.return_value = mock_submission

    # Mock QuestionValidator
    mock_validator.validate_submission_language.return_value = MagicMock()

    # Mock Question
    mock_question = MagicMock(spec=Question)
    mock_question.title = "Test Question"
    mock_testcase1 = MagicMock()
    mock_testcase1.id = uuid4()
    mock_testcase1.input = "input1"
    mock_testcase1.output = "output1"
    mock_testcase1.is_hidden = False
    mock_testcase1.weight = 1
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

    # Run
    from worker.evaluation import _evaluate_contest_submission_async

    await _evaluate_contest_submission_async(contest_id, evaluation_id, submission_id)

    # Asserts
    # delete_submission_testcases_batch should NOT be called
    mock_repo.delete_submission_testcases_batch.assert_not_called()
    # should run evaluation
    mock_run_evaluation.assert_called_once()
    # should update progress
    mock_update_progress.assert_called_once_with(contest_id, evaluation_id)
