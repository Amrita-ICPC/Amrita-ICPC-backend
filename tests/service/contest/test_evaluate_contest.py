from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.evaluation import EvaluationNotFoundError
from app.models.evaluation import Evaluation
from app.repositories.evaluation import EvaluationRepository
from app.schema.evaluation import EvaluationResponse, EvaluationStatusResponse
from app.utils.enums import ContestStatus


class TestEvaluateContest:
    @pytest.fixture
    def mock_evaluation_repository(self):
        repo = AsyncMock(spec=EvaluationRepository)
        repo.get_active_evaluation.return_value = None
        return repo

    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.fixture
    def contest_service_with_eval(
        self,
        contest_service,
        mock_evaluation_repository,
        mock_redis,
    ):
        contest_service.evaluation_repository = mock_evaluation_repository
        contest_service.redis = mock_redis
        return contest_service

    @pytest.mark.asyncio
    @patch("app.core.clients.celery.celery_app.send_task")
    async def test_evaluate_contest_success(
        self,
        mock_send_task,
        contest_service_with_eval,
        mock_contest_repository,
        mock_evaluation_repository,
        mock_redis,
        mock_guard,
        mock_contest,
        user_id,
    ):
        # Setup
        mock_contest.status = ContestStatus.PUBLISHED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest

        mock_submissions = [MagicMock(id=uuid4()) for _ in range(3)]
        mock_contest_repository.get_submissions_in_contest.return_value = (
            mock_submissions
        )

        evaluation_db_mock = MagicMock(spec=Evaluation)
        evaluation_db_mock.id = uuid4()
        evaluation_db_mock.contest_id = mock_contest.id
        evaluation_db_mock.is_evaluated = False
        evaluation_db_mock.total_submissions = 3
        evaluation_db_mock.processed_submissions = 0
        evaluation_db_mock.created_at = datetime.now(timezone.utc)
        evaluation_db_mock.created_by = user_id

        mock_evaluation_repository.create_evaluation.return_value = evaluation_db_mock

        # Run
        result = await contest_service_with_eval.evaluate_contest(
            mock_contest.id, user_id
        )

        # Assertions
        assert isinstance(result, EvaluationResponse)
        assert result.id == evaluation_db_mock.id
        assert result.is_evaluated is False

        mock_contest_repository.get_contest_or_raise.assert_called_once_with(
            mock_contest.id
        )
        mock_contest_repository.get_submissions_in_contest.assert_called_once_with(
            mock_contest.id
        )
        mock_guard.check_manage_contest.assert_called_once_with(
            user_id=user_id, contest=mock_contest
        )
        mock_evaluation_repository.create_evaluation.assert_called_once()

        # Verify redis.set call
        mock_redis.set.assert_called_once()
        redis_key, redis_value = mock_redis.set.call_args[0]
        assert redis_key == f"evaluation:{evaluation_db_mock.id}"

        import json

        redis_data = json.loads(redis_value)
        assert redis_data["processed"] == 0
        assert redis_data["total"] == 3
        assert redis_data["status"] == "PENDING"

        # Verify Celery send_task calls
        assert mock_send_task.call_count == 3
        for sub in mock_submissions:
            mock_send_task.assert_any_call(
                "worker.evaluation.evaluate_contest_submission",
                args=[str(evaluation_db_mock.id), str(sub.id)],
            )

        # Verify the Evaluation ORM model instantiation fields
        called_eval = mock_evaluation_repository.create_evaluation.call_args[0][0]
        assert isinstance(called_eval, Evaluation)
        assert called_eval.contest_id == mock_contest.id
        assert called_eval.is_evaluated is False
        assert called_eval.total_submissions == 3
        assert called_eval.created_by == user_id

    @pytest.mark.asyncio
    @patch("app.core.clients.celery.celery_app.send_task")
    async def test_evaluate_contest_cancels_active_evaluation(
        self,
        mock_send_task,
        contest_service_with_eval,
        mock_contest_repository,
        mock_evaluation_repository,
        mock_redis,
        mock_guard,
        mock_contest,
        user_id,
    ):
        # Setup
        mock_contest.status = ContestStatus.PUBLISHED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest

        mock_submissions = [MagicMock(id=uuid4()) for _ in range(3)]
        mock_contest_repository.get_submissions_in_contest.return_value = (
            mock_submissions
        )

        # Mock an active evaluation exists
        active_eval_mock = MagicMock(spec=Evaluation)
        active_eval_mock.id = uuid4()
        active_eval_mock.is_evaluated = False
        mock_evaluation_repository.get_active_evaluation.return_value = active_eval_mock

        # Mock Redis get for old key
        import json

        mock_redis.get.return_value = json.dumps(
            {"processed": 1, "total": 3, "status": "RUNNING"}
        )

        # New evaluation mock
        evaluation_db_mock = MagicMock(spec=Evaluation)
        evaluation_db_mock.id = uuid4()
        evaluation_db_mock.contest_id = mock_contest.id
        evaluation_db_mock.is_evaluated = False
        evaluation_db_mock.total_submissions = 3
        evaluation_db_mock.processed_submissions = 0
        evaluation_db_mock.created_at = datetime.now(timezone.utc)
        evaluation_db_mock.created_by = user_id
        mock_evaluation_repository.create_evaluation.return_value = evaluation_db_mock

        # Run
        result = await contest_service_with_eval.evaluate_contest(
            mock_contest.id, user_id
        )

        # Assertions
        assert result.id == evaluation_db_mock.id
        assert active_eval_mock.is_evaluated is True  # Marked as completed/superseded

        # Verify Redis update for the old key
        mock_redis.get.assert_called_with(f"evaluation:{active_eval_mock.id}")
        mock_redis.set.assert_any_call(
            f"evaluation:{active_eval_mock.id}",
            json.dumps({"processed": 1, "total": 3, "status": "COMPLETED"}),
        )

    @pytest.mark.asyncio
    async def test_evaluate_contest_not_found(
        self,
        contest_service_with_eval,
        mock_contest_repository,
        user_id,
    ):
        # Setup
        mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            "123"
        )

        # Run & Assert
        with pytest.raises(ContestNotFoundError):
            await contest_service_with_eval.evaluate_contest(uuid4(), user_id)

    @pytest.mark.asyncio
    async def test_evaluate_contest_deleted(
        self,
        contest_service_with_eval,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        # Setup
        mock_contest.status = ContestStatus.DELETED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest

        # Run & Assert
        with pytest.raises(ContestNotFoundError):
            await contest_service_with_eval.evaluate_contest(mock_contest.id, user_id)

    @pytest.mark.asyncio
    async def test_evaluate_contest_permission_denied(
        self,
        contest_service_with_eval,
        mock_contest_repository,
        mock_guard,
        mock_contest,
        user_id,
    ):
        # Setup
        mock_contest.status = ContestStatus.PUBLISHED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_guard.check_manage_contest.side_effect = PermissionDeniedError()

        # Run & Assert
        with pytest.raises(PermissionDeniedError):
            await contest_service_with_eval.evaluate_contest(mock_contest.id, user_id)

    @pytest.mark.asyncio
    async def test_get_evaluation_status_redis_hit(
        self,
        contest_service_with_eval,
        mock_contest_repository,
        mock_redis,
        mock_guard,
        mock_contest,
        user_id,
    ):
        # Setup
        evaluation_id = uuid4()
        mock_contest.status = ContestStatus.PUBLISHED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest

        import json

        redis_data = {
            "processed": 5,
            "total": 10,
            "status": "RUNNING",
        }
        mock_redis.get.return_value = json.dumps(redis_data)

        # Run
        result = await contest_service_with_eval.get_evaluation_status(
            mock_contest.id, evaluation_id, user_id
        )

        # Assertions
        assert isinstance(result, EvaluationStatusResponse)
        assert result.id == evaluation_id
        assert result.contest_id == mock_contest.id
        assert result.status == "RUNNING"
        assert result.total_submissions == 10
        assert result.processed_submissions == 5

        mock_redis.get.assert_called_once_with(f"evaluation:{evaluation_id}")
        mock_guard.check_manage_contest.assert_called_once_with(
            user_id=user_id, contest=mock_contest
        )

    @pytest.mark.asyncio
    async def test_get_evaluation_status_redis_miss_postgres_hit(
        self,
        contest_service_with_eval,
        mock_contest_repository,
        mock_evaluation_repository,
        mock_redis,
        mock_guard,
        mock_contest,
        user_id,
    ):
        # Setup
        evaluation_id = uuid4()
        mock_contest.status = ContestStatus.PUBLISHED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest

        # Redis miss
        mock_redis.get.return_value = None

        # Postgres hit
        evaluation_db_mock = MagicMock(spec=Evaluation)
        evaluation_db_mock.id = evaluation_id
        evaluation_db_mock.contest_id = mock_contest.id
        evaluation_db_mock.is_evaluated = True
        evaluation_db_mock.total_submissions = 10
        evaluation_db_mock.processed_submissions = 10
        evaluation_db_mock.created_at = datetime.now(timezone.utc)
        evaluation_db_mock.created_by = user_id

        mock_evaluation_repository.get_evaluation.return_value = evaluation_db_mock

        # Run
        result = await contest_service_with_eval.get_evaluation_status(
            mock_contest.id, evaluation_id, user_id
        )

        # Assertions
        assert isinstance(result, EvaluationStatusResponse)
        assert result.id == evaluation_id
        assert result.status == "COMPLETED"
        assert result.total_submissions == 10
        assert result.processed_submissions == 10

        mock_redis.get.assert_called_once_with(f"evaluation:{evaluation_id}")
        mock_evaluation_repository.get_evaluation.assert_called_once_with(evaluation_id)
        mock_guard.check_manage_contest.assert_called_once_with(
            user_id=user_id, contest=mock_contest
        )

    @pytest.mark.asyncio
    async def test_get_evaluation_status_not_found(
        self,
        contest_service_with_eval,
        mock_contest_repository,
        mock_evaluation_repository,
        mock_redis,
        mock_contest,
        user_id,
    ):
        # Setup
        evaluation_id = uuid4()
        mock_contest.status = ContestStatus.PUBLISHED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest

        mock_redis.get.return_value = None
        mock_evaluation_repository.get_evaluation.return_value = None

        # Run & Assert
        with pytest.raises(EvaluationNotFoundError):
            await contest_service_with_eval.get_evaluation_status(
                mock_contest.id, evaluation_id, user_id
            )

    @pytest.mark.asyncio
    async def test_get_evaluation_status_permission_denied(
        self,
        contest_service_with_eval,
        mock_contest_repository,
        mock_guard,
        mock_contest,
        user_id,
    ):
        # Setup
        evaluation_id = uuid4()
        mock_contest.status = ContestStatus.PUBLISHED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_guard.check_manage_contest.side_effect = PermissionDeniedError()

        # Run & Assert
        with pytest.raises(PermissionDeniedError):
            await contest_service_with_eval.get_evaluation_status(
                mock_contest.id, evaluation_id, user_id
            )
