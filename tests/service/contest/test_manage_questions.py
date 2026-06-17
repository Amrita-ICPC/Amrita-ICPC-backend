"""Unit tests for contest question management in ContestQuestionService."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.exceptions.question import InvalidQuestionError
from app.models.question import Question
from app.repositories.language import LanguageRepository
from app.repositories.question import QuestionRepository
from app.schema.question import (
    QuestionListSummaryResponse,
    QuestionResponse,
    QuestionTemplateCreate,
    QuestionTestCaseCreate,
    QuestionUpdate,
)
from app.service.contest_question_service import ContestQuestionService
from app.utils.enums import QuestionDifficulty


@pytest.fixture
def mock_bank_repository() -> AsyncMock:
    """Mock bank repository for contest-question service methods."""
    from app.repositories.bank import BankRepository

    return AsyncMock(spec=BankRepository)


@pytest.fixture
def mock_question_repository() -> AsyncMock:
    """Mock question repository for contest-question service methods."""
    return AsyncMock(spec=QuestionRepository)


@pytest.fixture
def mock_language_repository() -> AsyncMock:
    """Mock language repository for validating platform languages."""
    language_repository = AsyncMock(spec=LanguageRepository)
    language_repository.get_existing_ids.return_value = set()
    return language_repository


@pytest.fixture
def contest_service_with_questions(
    mock_contest_repository: AsyncMock,
    mock_guard: AsyncMock,
    mock_validator: AsyncMock,
    mock_question_repository: AsyncMock,
    mock_language_repository: AsyncMock,
    mock_bank_repository: AsyncMock,
) -> ContestQuestionService:
    """ContestQuestionService instance with question repository wired."""
    return ContestQuestionService(
        repository=mock_contest_repository,
        guard=mock_guard,
        validator=mock_validator,
        question_repository=mock_question_repository,
        language_repository=mock_language_repository,
        bank_repository=mock_bank_repository,
    )


@pytest.fixture
def mock_question(user_id):
    """Mock question with one testcase and one template."""
    question = MagicMock(spec=Question)
    question.id = uuid4()
    question.title = "Sample Title"
    question.question_text = "Sample question"
    question.difficulty = QuestionDifficulty.EASY
    question.time_limit_ms = 1000
    question.memory_limit_mb = 256
    question.created_by = user_id
    question.created_at = datetime.now(timezone.utc)
    question.updated_at = datetime.now(timezone.utc)
    question.languages = []

    tag = MagicMock()
    tag.tag = MagicMock()
    tag.tag.id = uuid4()
    tag.tag.name = "Sample Tag"
    question.tags = [tag]

    testcase = MagicMock()
    testcase.id = uuid4()
    testcase.input = "1"
    testcase.output = "1"
    testcase.is_hidden = False
    testcase.weight = 1
    testcase.order = 0

    template = MagicMock()
    template.id = uuid4()
    template.language_id = 71
    template.starter_code = "start"
    template.driver_code = None
    template.solution_code = None

    question.testcases = [testcase]
    question.templates = [template]
    return question


@pytest.mark.asyncio
async def test_get_contest_questions_returns_paginated_summaries(
    contest_service_with_questions: ContestQuestionService,
    mock_contest_repository: AsyncMock,
    mock_guard: AsyncMock,
    mock_contest,
    mock_question,
    user_id,
):
    """get_contest_questions should validate read permission and map summaries."""
    from app.repositories.dto import ContestQuestionsPaginatedResult
    from app.schema.question import ContestQuestionsListResponse

    contest_id = mock_contest.id
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.get_contest_questions_paginated.return_value = (
        ContestQuestionsPaginatedResult(
            total=1,
            items=[mock_question],
            easy_count=1,
            medium_count=0,
            hard_count=0,
        )
    )

    mapped_summary = MagicMock(spec=QuestionListSummaryResponse)
    with patch.object(
        QuestionListSummaryResponse,
        "from_question",
        return_value=mapped_summary,
    ):
        result = await contest_service_with_questions.get_contest_questions(
            contest_id=contest_id,
            user_id=user_id,
            search_term="sample",
            difficulty=QuestionDifficulty.EASY,
            language_id=71,
            tag_id=uuid4(),
            skip=10,
            limit=5,
        )

    assert isinstance(result, ContestQuestionsListResponse)
    assert result.total_count == 1
    assert result.questions == [mapped_summary]
    assert result.easy_count == 1
    assert result.medium_count == 0
    assert result.hard_count == 0
    mock_guard.check_read_contest.assert_called_once_with(
        user_id=user_id,
        contest=mock_contest,
    )


@pytest.mark.asyncio
async def test_get_contest_question_returns_question_response(
    contest_service_with_questions: ContestQuestionService,
    mock_contest_repository: AsyncMock,
    mock_question_repository: AsyncMock,
    mock_guard: AsyncMock,
    mock_contest,
    mock_question,
    user_id,
):
    """get_contest_question should enforce manage permission via helper and map response."""
    contest_id = mock_contest.id
    question_id = mock_question.id

    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.is_question_in_contest.return_value = True
    mock_question_repository.get_question_or_raise.return_value = mock_question

    mapped_response = MagicMock(spec=QuestionResponse)
    with patch.object(QuestionResponse, "from_question", return_value=mapped_response):
        result = await contest_service_with_questions.get_contest_question(
            contest_id=contest_id,
            question_id=question_id,
            user_id=user_id,
        )

    assert result == mapped_response
    mock_guard.check_read_contest.assert_called_once_with(
        user_id=user_id,
        contest=mock_contest,
    )


@pytest.mark.asyncio
async def test_update_single_testcase_supports_partial_payload(
    contest_service_with_questions: ContestQuestionService,
    mock_contest_repository: AsyncMock,
    mock_question_repository: AsyncMock,
    mock_language_repository: AsyncMock,
    mock_contest,
    mock_question,
    user_id,
):
    """Question update should replace testcases with provided list."""
    contest_id = mock_contest.id
    question_id = mock_question.id

    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.is_question_in_contest.return_value = True
    mock_question_repository.get_question_or_raise.return_value = mock_question
    mock_question_repository.update_question.return_value = mock_question
    mock_language_repository.get_existing_ids.return_value = set()

    original_input = mock_question.testcases[0].input
    original_output = mock_question.testcases[0].output
    payload = QuestionUpdate(
        testcases=[
            QuestionTestCaseCreate(
                input=original_input,
                output=original_output,
                is_hidden=True,
                weight=mock_question.testcases[0].weight,
                order=mock_question.testcases[0].order,
            )
        ]
    )

    with patch.object(QuestionResponse, "from_question", return_value=MagicMock()):
        await contest_service_with_questions.update_contest_question(
            contest_id=contest_id,
            question_id=question_id,
            update_data=payload,
            user_id=user_id,
        )

    mock_question_repository.update_question_testcases.assert_called_once()
    args, kwargs = mock_question_repository.update_question_testcases.call_args
    assert args[0] == mock_question
    assert args[1][0].is_hidden is True
    assert args[1][0].input == original_input
    mock_question_repository.update_question.assert_called_once_with(mock_question)


@pytest.mark.asyncio
async def test_update_single_testcase_raises_when_missing(
    contest_service_with_questions: ContestQuestionService,
    mock_contest_repository: AsyncMock,
    mock_question_repository: AsyncMock,
    mock_language_repository: AsyncMock,
    mock_contest,
    mock_question,
    user_id,
):
    """Question update should reject empty testcase payloads."""
    contest_id = mock_contest.id
    question_id = mock_question.id

    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.is_question_in_contest.return_value = True
    mock_question_repository.get_question_or_raise.return_value = mock_question
    mock_language_repository.get_existing_ids.return_value = set()

    with pytest.raises(InvalidQuestionError):
        await contest_service_with_questions.update_contest_question(
            contest_id=contest_id,
            question_id=question_id,
            update_data=QuestionUpdate(testcases=[]),
            user_id=user_id,
        )


@pytest.mark.asyncio
async def test_update_single_template_supports_partial_payload(
    contest_service_with_questions: ContestQuestionService,
    mock_contest_repository: AsyncMock,
    mock_question_repository: AsyncMock,
    mock_language_repository: AsyncMock,
    mock_contest,
    mock_question,
    user_id,
):
    """Question update should replace templates with provided list."""
    contest_id = mock_contest.id
    question_id = mock_question.id

    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.is_question_in_contest.return_value = True
    mock_question_repository.get_question_or_raise.return_value = mock_question
    mock_question_repository.update_question.return_value = mock_question
    mock_language_repository.get_existing_ids.return_value = {
        mock_question.templates[0].language_id
    }

    old_language_id = mock_question.templates[0].language_id
    payload = QuestionUpdate(
        templates=[
            QuestionTemplateCreate(
                language_id=old_language_id,
                starter_code="updated-starter",
                driver_code=mock_question.templates[0].driver_code,
                solution_code=mock_question.templates[0].solution_code,
            )
        ]
    )

    with patch.object(QuestionResponse, "from_question", return_value=MagicMock()):
        await contest_service_with_questions.update_contest_question(
            contest_id=contest_id,
            question_id=question_id,
            update_data=payload,
            user_id=user_id,
        )

    mock_question_repository.update_question_templates.assert_called_once()
    args, kwargs = mock_question_repository.update_question_templates.call_args
    assert args[0] == mock_question
    assert args[1][0].starter_code == "updated-starter"
    assert args[1][0].language_id == old_language_id
    mock_question_repository.update_question.assert_called_once_with(mock_question)


@pytest.mark.asyncio
async def test_update_single_template_raises_on_duplicate_language(
    contest_service_with_questions: ContestQuestionService,
    mock_contest_repository: AsyncMock,
    mock_question_repository: AsyncMock,
    mock_language_repository: AsyncMock,
    mock_contest,
    mock_question,
    user_id,
):
    """Question update should reject duplicate template language IDs."""
    contest_id = mock_contest.id
    question_id = mock_question.id

    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.is_question_in_contest.return_value = True
    mock_question_repository.get_question_or_raise.return_value = mock_question
    mock_language_repository.get_existing_ids.return_value = {62, 71}

    with pytest.raises(InvalidQuestionError):
        await contest_service_with_questions.update_contest_question(
            contest_id=contest_id,
            question_id=question_id,
            update_data=QuestionUpdate(
                templates=[
                    QuestionTemplateCreate(
                        language_id=62,
                        starter_code="first",
                    ),
                    QuestionTemplateCreate(
                        language_id=62,
                        starter_code="duplicate",
                    ),
                ]
            ),
            user_id=user_id,
        )


@pytest.mark.asyncio
async def test_add_questions_to_contest_automatic_order(
    contest_service_with_questions: ContestQuestionService,
    mock_contest_repository: AsyncMock,
    mock_question_repository: AsyncMock,
    mock_guard: AsyncMock,
    mock_contest,
    user_id,
):
    """add_questions_to_contest should automatically calculate order if not provided."""
    from app.schema.contest import AddContestQuestionRequest, AddContestQuestionsRequest

    contest_id = mock_contest.id
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.get_max_question_order.return_value = 5
    mock_contest_repository.get_ordered_question_orders_for_contest.return_value = [
        MagicMock(order=1),
        MagicMock(order=3),
        MagicMock(order=5),
    ]
    mock_contest_repository.is_question_in_contest.return_value = False
    mock_question_repository.get_question_or_raise.return_value = MagicMock()
    mock_contest_repository.add_questions_to_contest.return_value = []

    request = AddContestQuestionsRequest(
        questions=[
            AddContestQuestionRequest(
                question_id=uuid4(),
                duration=300,
                score=100,
                order=10,  # Manual higher than max
            ),
            AddContestQuestionRequest(
                question_id=uuid4(),
                duration=300,
                score=100,
                order=None,  # Automatic
            ),
        ]
    )

    await contest_service_with_questions.add_questions_to_contest(
        contest_id, request, user_id
    )

    add_call = mock_contest_repository.add_questions_to_contest.call_args
    dto_list = add_call[0][0]

    assert len(dto_list) == 2
    assert dto_list[0].order == 10
    assert dto_list[1].order == 11  # Should be max(10, 5) + 1 = 11


@pytest.mark.asyncio
async def test_add_questions_to_contest_automatic_order_conflicts(
    contest_service_with_questions: ContestQuestionService,
    mock_contest_repository: AsyncMock,
    mock_question_repository: AsyncMock,
    mock_guard: AsyncMock,
    mock_contest,
    user_id,
):
    """add_questions_to_contest should avoid order conflicts in batch."""
    from app.schema.contest import AddContestQuestionRequest, AddContestQuestionsRequest

    contest_id = mock_contest.id
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.get_max_question_order.return_value = 2
    mock_contest_repository.get_ordered_question_orders_for_contest.return_value = [
        MagicMock(order=1),
        MagicMock(order=2),
    ]
    mock_contest_repository.is_question_in_contest.return_value = False
    mock_question_repository.get_question_or_raise.return_value = MagicMock()
    mock_contest_repository.add_questions_to_contest.return_value = []

    request = AddContestQuestionsRequest(
        questions=[
            AddContestQuestionRequest(
                question_id=uuid4(),
                duration=300,
                score=100,
                order=3,  # Manual
            ),
            AddContestQuestionRequest(
                question_id=uuid4(),
                duration=300,
                score=100,
                order=None,  # Automatic, should become 4
            ),
        ]
    )

    await contest_service_with_questions.add_questions_to_contest(
        contest_id, request, user_id
    )

    add_call = mock_contest_repository.add_questions_to_contest.call_args
    dto_list = add_call[0][0]

    assert dto_list[0].order == 3
    assert dto_list[1].order == 4  # Max was 2, manual was 3, so automatic should be 4


@pytest.mark.asyncio
async def test_add_questions_to_contest_optional_fields(
    contest_service_with_questions: ContestQuestionService,
    mock_contest_repository: AsyncMock,
    mock_question_repository: AsyncMock,
    mock_guard: AsyncMock,
    mock_contest,
    user_id,
):
    """add_questions_to_contest should support optional duration and score."""
    from app.schema.contest import AddContestQuestionRequest, AddContestQuestionsRequest

    contest_id = mock_contest.id
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.get_max_question_order.return_value = 0
    mock_contest_repository.get_ordered_question_orders_for_contest.return_value = []
    mock_contest_repository.is_question_in_contest.return_value = False
    mock_question_repository.get_question_or_raise.return_value = MagicMock()
    mock_contest_repository.add_questions_to_contest.return_value = []

    request = AddContestQuestionsRequest(
        questions=[
            AddContestQuestionRequest(
                question_id=uuid4(),
                duration=None,  # Optional
                score=None,  # Optional
                order=1,
            )
        ]
    )

    await contest_service_with_questions.add_questions_to_contest(
        contest_id, request, user_id
    )

    add_call = mock_contest_repository.add_questions_to_contest.call_args
    dto_list = add_call[0][0]

    assert len(dto_list) == 1
    assert dto_list[0].duration is None
    assert dto_list[0].score is None
