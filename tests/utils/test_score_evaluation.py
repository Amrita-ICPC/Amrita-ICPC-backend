import uuid
from unittest.mock import MagicMock

from app.models.question import SubmissionTestCase
from app.models.question import TestCase as QuestionTestCase
from app.utils.enums import SubmissionStatus
from app.utils.evaluation import (
    calculate_score_from_weights,
    calculate_submission_score,
)


def test_calculate_score_from_weights_empty() -> None:
    # No testcases
    score = calculate_score_from_weights(
        total_score=100, testcases=[], passed_testcase_ids=set()
    )
    assert score == 0


def test_calculate_score_from_weights_zero_total_weight() -> None:
    # Testcases have 0 weight
    tc1 = MagicMock(spec=QuestionTestCase)
    tc1.id = uuid.uuid4()
    tc1.weight = 0

    score = calculate_score_from_weights(
        total_score=100, testcases=[tc1], passed_testcase_ids={tc1.id}
    )
    assert score == 0


def test_calculate_score_from_weights_all_passed() -> None:
    # All testcases pass, equal weights
    id1, id2 = uuid.uuid4(), uuid.uuid4()
    tc1 = MagicMock(spec=QuestionTestCase)
    tc1.id = id1
    tc1.weight = 1

    tc2 = MagicMock(spec=QuestionTestCase)
    tc2.id = id2
    tc2.weight = 1

    score = calculate_score_from_weights(
        total_score=100, testcases=[tc1, tc2], passed_testcase_ids={id1, id2}
    )
    assert score == 100


def test_calculate_score_from_weights_partial_passed() -> None:
    # Partial pass, custom weights
    id1, id2, id3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tc1 = MagicMock(spec=QuestionTestCase)
    tc1.id = id1
    tc1.weight = 2  # Passed

    tc2 = MagicMock(spec=QuestionTestCase)
    tc2.id = id2
    tc2.weight = 3  # Failed

    tc3 = MagicMock(spec=QuestionTestCase)
    tc3.id = id3
    tc3.weight = 5  # Passed

    # Total weight = 10, passed weight = 7. Expected score = (7/10) * 100 = 70.
    score = calculate_score_from_weights(
        total_score=100, testcases=[tc1, tc2, tc3], passed_testcase_ids={id1, id3}
    )
    assert score == 70


def test_calculate_score_from_weights_rounding() -> None:
    # Test rounding (e.g. 1 out of 3 passed, total_score = 100)
    # 1/3 * 100 = 33.333 -> 33
    id1, id2, id3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tc1 = MagicMock(spec=QuestionTestCase)
    tc1.id = id1
    tc1.weight = 1

    tc2 = MagicMock(spec=QuestionTestCase)
    tc2.id = id2
    tc2.weight = 1

    tc3 = MagicMock(spec=QuestionTestCase)
    tc3.id = id3
    tc3.weight = 1

    score = calculate_score_from_weights(
        total_score=100, testcases=[tc1, tc2, tc3], passed_testcase_ids={id1}
    )
    assert score == 33

    # 2/3 * 100 = 66.667 -> 67
    score_2 = calculate_score_from_weights(
        total_score=100, testcases=[tc1, tc2, tc3], passed_testcase_ids={id1, id2}
    )
    assert score_2 == 67


def test_calculate_submission_score() -> None:
    # Test calculate_submission_score with actual list of SubmissionTestCase
    id1, id2 = uuid.uuid4(), uuid.uuid4()
    tc1 = MagicMock(spec=QuestionTestCase)
    tc1.id = id1
    tc1.weight = 1

    tc2 = MagicMock(spec=QuestionTestCase)
    tc2.id = id2
    tc2.weight = 4

    # Submission test cases results
    res1 = MagicMock(spec=SubmissionTestCase)
    res1.testcase_id = id1
    res1.status = SubmissionStatus.AC

    res2 = MagicMock(spec=SubmissionTestCase)
    res2.testcase_id = id2
    res2.status = SubmissionStatus.WA

    # Total weight = 5, passed = 1. Expected score = (1/5) * 100 = 20
    score = calculate_submission_score(
        total_score=100, testcases=[tc1, tc2], testcase_results=[res1, res2]
    )
    assert score == 20
