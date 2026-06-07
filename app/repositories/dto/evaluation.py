import dataclasses

from app.models.question import SubmissionTestCase
from app.utils.enums import SubmissionStatus


@dataclasses.dataclass
class EvaluationResult:
    """Result of evaluating a submission."""

    status: SubmissionStatus
    passed_testcases: int
    total_testcases: int
    total_time: int
    total_memory: int
    testcase_results: list[SubmissionTestCase]
