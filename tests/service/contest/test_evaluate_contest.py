import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.evaluation import EvaluationNotFoundError
from app.schema.evaluation import EvaluationResponse, EvaluationStatusResponse
from app.utils.enums import ContestStatus


class TestEvaluateContest:
    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.fixture
    def contest_service_with_redis(
        self,
        contest_service,
        mock_redis,
    ):
        contest_service.redis = mock_redis
        return contest_service

    @pytest.mark.asyncio
    @patch("app.core.clients.celery.celery_app.send_task")
    async def test_evaluate_contest_success(
        self,
        mock_send_task,
        contest_service_with_redis,
        mock_contest_repository,
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

        # Run
        result = await contest_service_with_redis.evaluate_contest(
            mock_contest.id, user_id
        )

        # Assertions
        assert isinstance(result, EvaluationResponse)
        assert result.is_evaluated is False
        assert result.total_submissions == 3

        mock_contest_repository.get_contest_or_raise.assert_called_once_with(
            mock_contest.id
        )
        mock_contest_repository.get_submissions_in_contest.assert_called_once_with(
            mock_contest.id
        )
        mock_guard.check_manage_contest.assert_called_once_with(
            user_id=user_id, contest=mock_contest
        )

        # Verify redis.set call
        mock_redis.set.assert_called_once()
        redis_key, redis_value = mock_redis.set.call_args[0]
        assert redis_key == f"contests:{mock_contest.id}:evaluation"

        redis_data = json.loads(redis_value)
        assert redis_data["id"] == str(result.id)
        assert redis_data["processed_submissions"] == 0
        assert redis_data["total_submissions"] == 3
        assert redis_data["status"] == "PENDING"

        # Verify Celery send_task calls
        assert mock_send_task.call_count == 3
        for sub in mock_submissions:
            mock_send_task.assert_any_call(
                "worker.evaluation.evaluate_contest_submission",
                args=[str(mock_contest.id), str(result.id), str(sub.id)],
            )

    @pytest.mark.asyncio
    @patch("app.core.clients.celery.celery_app.send_task")
    async def test_evaluate_contest_empty_submissions(
        self,
        mock_send_task,
        contest_service_with_redis,
        mock_contest_repository,
        mock_redis,
        mock_guard,
        mock_contest,
        user_id,
    ):
        # Setup
        mock_contest.status = ContestStatus.PUBLISHED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest_repository.get_submissions_in_contest.return_value = []

        # Run
        result = await contest_service_with_redis.evaluate_contest(
            mock_contest.id, user_id
        )

        # Assertions
        assert isinstance(result, EvaluationResponse)
        assert result.is_evaluated is True
        assert result.total_submissions == 0

        mock_redis.set.assert_called_once()
        redis_key, redis_value = mock_redis.set.call_args[0]
        assert redis_key == f"contests:{mock_contest.id}:evaluation"
        redis_data = json.loads(redis_value)
        assert redis_data["status"] == "COMPLETED"

        mock_send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_evaluate_contest_not_found(
        self,
        contest_service_with_redis,
        mock_contest_repository,
        user_id,
    ):
        # Setup
        mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            "123"
        )

        # Run & Assert
        with pytest.raises(ContestNotFoundError):
            await contest_service_with_redis.evaluate_contest(uuid4(), user_id)

    @pytest.mark.asyncio
    async def test_evaluate_contest_deleted(
        self,
        contest_service_with_redis,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        # Setup
        mock_contest.status = ContestStatus.DELETED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest

        # Run & Assert
        with pytest.raises(ContestNotFoundError):
            await contest_service_with_redis.evaluate_contest(mock_contest.id, user_id)

    @pytest.mark.asyncio
    async def test_evaluate_contest_permission_denied(
        self,
        contest_service_with_redis,
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
            await contest_service_with_redis.evaluate_contest(mock_contest.id, user_id)

    @pytest.mark.asyncio
    async def test_get_evaluation_status_redis_hit(
        self,
        contest_service_with_redis,
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

        redis_data = {
            "id": str(evaluation_id),
            "contest_id": str(mock_contest.id),
            "total_submissions": 10,
            "processed_submissions": 5,
            "status": "RUNNING",
        }
        mock_redis.get.return_value = json.dumps(redis_data)

        # Run
        result = await contest_service_with_redis.get_evaluation_status(
            mock_contest.id, user_id
        )

        # Assertions
        assert isinstance(result, EvaluationStatusResponse)
        assert result.id == evaluation_id
        assert result.contest_id == mock_contest.id
        assert result.status == "RUNNING"
        assert result.total_submissions == 10
        assert result.processed_submissions == 5

        mock_redis.get.assert_called_once_with(f"contests:{mock_contest.id}:evaluation")
        mock_guard.check_manage_contest.assert_called_once_with(
            user_id=user_id, contest=mock_contest
        )

    @pytest.mark.asyncio
    async def test_get_evaluation_status_not_found(
        self,
        contest_service_with_redis,
        mock_contest_repository,
        mock_redis,
        mock_contest,
        user_id,
    ):
        # Setup
        mock_contest.status = ContestStatus.PUBLISHED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_redis.get.return_value = None

        # Run & Assert
        with pytest.raises(EvaluationNotFoundError):
            await contest_service_with_redis.get_evaluation_status(
                mock_contest.id, user_id
            )

    @pytest.mark.asyncio
    async def test_get_evaluation_status_permission_denied(
        self,
        contest_service_with_redis,
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
            await contest_service_with_redis.get_evaluation_status(
                mock_contest.id, user_id
            )
