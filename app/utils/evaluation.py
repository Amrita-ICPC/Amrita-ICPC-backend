import uuid
from typing import Collection, Sequence

from app.models.question import SubmissionTestCase, TestCase
from app.utils.enums import SubmissionStatus


def calculate_score_from_weights(
    total_score: int,
    testcases: Sequence[TestCase],
    passed_testcase_ids: Collection[uuid.UUID],
) -> int:
    """
    Calculate the score of a submission based on testcase weights.

    Args:
        total_score: The maximum possible score for the question.
        testcases: The sequence of TestCase models associated with the question.
        passed_testcase_ids: The set or list of testcase IDs that were successfully passed (AC).

    Returns:
        int: The calculated score, rounded to the nearest integer.
    """
    if not testcases:
        return 0

    total_weight = sum(tc.weight if tc.weight is not None else 1 for tc in testcases)
    if total_weight <= 0:
        return 0

    passed_ids_set = set(passed_testcase_ids)
    passed_weight = sum(
        tc.weight if tc.weight is not None else 1
        for tc in testcases
        if tc.id in passed_ids_set
    )

    # Calculate score proportionally and round to nearest integer
    score = (passed_weight / total_weight) * total_score
    return round(score)


def calculate_submission_score(
    total_score: int,
    testcases: Sequence[TestCase],
    testcase_results: Sequence[SubmissionTestCase],
) -> int:
    """
    Calculate the score of a submission based on TestCase weights and SubmissionTestCase results.

    Args:
        total_score: The maximum possible score for the question.
        testcases: The sequence of TestCase models associated with the question.
        testcase_results: The sequence of SubmissionTestCase results for the submission.

    Returns:
        int: The calculated score, rounded to the nearest integer.
    """
    passed_testcase_ids = {
        res.testcase_id for res in testcase_results if res.status == SubmissionStatus.AC
    }
    return calculate_score_from_weights(total_score, testcases, passed_testcase_ids)
