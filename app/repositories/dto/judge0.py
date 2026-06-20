"""Data Transfer Objects for Judge0 operations."""

import dataclasses
from typing import Optional

from app.core.clients.judge0 import Judge0StatusCode


@dataclasses.dataclass
class Judge0CompilationErrorDTO:
    """Code compilation error - execution cannot proceed.

    When code fails to compile, all test cases are skipped.
    This is an early exit scenario, not a per-testcase result.
    """

    compile_output: str
    """Compilation error details (syntax error, import error, etc.)."""

    message: str
    """Error message (e.g., 'Compilation Error')."""

    status: Judge0StatusCode = Judge0StatusCode.COMPILATION_ERROR
    """Always COMPILATION_ERROR for this DTO."""


@dataclasses.dataclass
class Judge0ExecutionResultDTO:
    """Individual test case execution result from Judge0.

    Only created when code compiles successfully.
    Compilation errors are handled separately via Judge0CompilationErrorDTO.
    Includes question context for mapping back to original request.
    """

    question_id: str
    """Question UUID this result belongs to."""

    testcase_id: str
    """Test case ID being executed."""

    status: Judge0StatusCode
    """Execution status (ACCEPTED, WRONG_ANSWER, RUNTIME_ERROR, TIME_LIMIT_EXCEEDED, INTERNAL_ERROR).

    Note: COMPILATION_ERROR is NOT included here - use Judge0CompilationErrorDTO instead.
    """

    passed: bool = False
    """Whether this test case passed (stdout == expected_output)."""

    stdout: Optional[str] = None
    """Standard output from the execution."""

    stderr: Optional[str] = None
    """Standard error output (runtime errors like ZeroDivisionError, IndexError, etc.)."""

    expected_output: Optional[str] = None
    """Expected output for comparison (from TestCase.output)."""

    time: Optional[float] = None
    """Execution time in seconds."""

    memory: Optional[int] = None
    """Memory used in kilobytes."""

    @property
    def is_completed(self) -> bool:
        """Check if execution is completed (not in queue or processing)."""
        return self.status not in (
            Judge0StatusCode.IN_QUEUE,
            Judge0StatusCode.PROCESSING,
        )

    @property
    def is_success(self) -> bool:
        """Check if execution was successful (accepted)."""
        return self.status == Judge0StatusCode.ACCEPTED


@dataclasses.dataclass
class Judge0SubmissionDTO:
    """Judge0 API submission/execution result."""

    token: str
    """Judge0 submission token (unique ID)."""

    status_id: Optional[int] = None
    """Status code ID from Judge0 (nullable - may be None if Judge0 omits it)."""

    stdout: Optional[str] = None
    """Standard output."""

    stderr: Optional[str] = None
    """Standard error output."""

    time: Optional[float] = None
    """Execution time in seconds."""

    memory: Optional[int] = None
    """Memory used in kilobytes."""

    compile_output: Optional[str] = None
    """Compilation output."""

    message: Optional[str] = None
    """Status message."""

    def __post_init__(self) -> None:
        if self.time is not None and not isinstance(self.time, float):
            try:
                self.time = float(self.time)
            except (ValueError, TypeError):
                self.time = None
        if self.memory is not None and not isinstance(self.memory, int):
            try:
                self.memory = int(self.memory)
            except (ValueError, TypeError):
                self.memory = None

    @property
    def status(self) -> Judge0StatusCode:
        """Convert status_id to Judge0StatusCode enum."""
        if self.status_id is None:
            from app.exceptions.judge0 import Judge0ClientError

            raise Judge0ClientError(
                f"Invalid Judge0 response: status_id is None. "
                f"Full submission data: {self}"
            )
        try:
            return Judge0StatusCode(self.status_id)
        except ValueError as e:
            from app.exceptions.judge0 import Judge0ClientError

            raise Judge0ClientError(
                f"Unknown Judge0 status code: {self.status_id}. Error: {e}"
            )

    @property
    def is_completed(self) -> bool:
        """Check if submission is completed."""
        return self.status not in (
            Judge0StatusCode.IN_QUEUE,
            Judge0StatusCode.PROCESSING,
        )


@dataclasses.dataclass
class Judge0ExecutionRequestDTO:
    """Request DTO for submitting code to Judge0 for execution.

    Contains the code and context needed to execute against test cases.
    Repository uses question_id to fetch corresponding non-hidden test cases.
    """

    question_id: str
    """Question UUID - used to fetch corresponding test cases."""

    source_code: str
    """Source code to execute."""

    language_id: int
    """Judge0 language ID (e.g., 71 for Python 3.10)."""

    cpu_time_limit: Optional[float] = None
    """CPU time limit in seconds. When None, the Judge0 instance default applies."""

    wall_time_limit: Optional[float] = None
    """Wall-clock time limit in seconds. When None, the Judge0 instance default applies."""

    memory_limit: Optional[int] = None
    """Memory limit in kilobytes. When None, the Judge0 instance default applies."""

    stack_limit: Optional[int] = None
    """Stack size limit in kilobytes. When None, the Judge0 instance default applies."""
