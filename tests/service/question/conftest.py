from unittest.mock import MagicMock, patch

import pytest

from app.schema.question import QuestionCreate
from app.utils.enums import QuestionDifficulty


@pytest.fixture
def mock_repository():
    from app.repositories.question import QuestionRepository

    return MagicMock(spec=QuestionRepository)


@pytest.fixture
def mock_validator():
    from app.validators.question import QuestionValidator

    return MagicMock(spec=QuestionValidator)


@pytest.fixture
def mock_guard():
    from app.core.guards.question import QuestionOperationGuard

    return MagicMock(spec=QuestionOperationGuard)


@pytest.fixture
def question_service(mock_repository, mock_guard, mock_validator):
    with (
        patch(
            "app.core.cache.decorators.cache_get",
            side_effect=lambda **kwargs: lambda func: func,
        ),
        patch(
            "app.core.cache.decorators.cache_delete",
            side_effect=lambda **kwargs: lambda func: func,
        ),
    ):
        from app.service.question_service import QuestionService

        service = QuestionService(
            repository=mock_repository,
            guard=mock_guard,
            validator=mock_validator,
        )
        yield service


@pytest.fixture
def sample_question_data():
    return QuestionCreate(
        question_text="Sample Question",
        difficulty=QuestionDifficulty.EASY,
        allowed_languages=["python", "cpp"],
        testcases=[{"input": "1", "output": "1", "is_hidden": False}],
        time_limit_ms=1000,
        memory_limit_mb=256,
    )
