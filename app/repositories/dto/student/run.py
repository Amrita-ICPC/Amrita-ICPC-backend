"""Data Transfer Objects for student code execution (run/test endpoint).

These DTOs handle the flow of data for code runs:
1. Student requests to test/run their code against a test case
2. Execution results returned from Judge0
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class StudentCodeRunRequestDTO:
    """Request DTO for student to test/run their code.

    Student provides code, language, and optionally a specific test case.
    Used for quick testing before submission.
    """

    user_id: UUID
    """UUID of student running the code."""

    contest_id: UUID
    """UUID of contest where problem is."""

    question_id: UUID
    """UUID of the question/problem."""

    code: str
    """Source code to execute."""

    language_id: int
    """Judge0 language ID (54=Python, 71=Java, etc)."""

    testcase_id: UUID | None = None
    """Optional specific test case to run. If None, run first test case."""


@dataclass
class StudentTestCaseRunResultDTO:
    """Result DTO for a single test case execution.

    Contains verdict and execution details from Judge0.
    """

    testcase_id: UUID
    """Which test case was executed."""

    passed: bool
    """Whether test case passed (Accepted verdict)."""

    status_code: int
    """Judge0 status code (1=AC, 2=WA, 3=TLE, etc)."""

    status_description: str
    """Readable status (Accepted, Wrong Answer, Time Limit Exceeded, etc)."""

    time: float
    """Execution time in seconds."""

    memory: float
    """Memory used in MB."""

    stdout: str | None
    """Code output."""

    stderr: str | None
    """Error output if any."""

    compile_output: str | None
    """Compilation error if any."""

    expected_output: str | None
    """What output was expected (for debugging)."""


@dataclass
class StudentCodeRunResponseDTO:
    """Complete response DTO for a code run operation.

    Contains result of running code against all non-hidden test cases.
    """

    question_id: UUID
    """Problem that was tested."""

    results: list[StudentTestCaseRunResultDTO]
    """Execution result details for each test case."""

    message: str
    """Success/error message."""

    passed: bool
    """Overall pass status."""
