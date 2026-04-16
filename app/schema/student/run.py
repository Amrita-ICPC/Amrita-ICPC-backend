"""Pydantic schemas for student code run/test endpoint.

Request schemas: What students send to test their code
Response schemas: What server returns after execution
"""

from __future__ import annotations

from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class StudentCodeRunRequest(BaseModel):
    """Request to test/run code against a test case.
    
    Student submits code and specifies which test case to run against.
    This is for quick testing before official submission.
    
    Example:
        ```json
        {
            "code": "print('hello')",
            "language_id": 54,
            "testcase_id": "550e8400-e29b-41d4-a716-446655440000"
        }
        ```
    """

    code: str = Field(..., min_length=1, description="Source code to execute")
    """Source code student wrote."""

    language_id: int = Field(
        ...,
        gt=0,
        description="Judge0 language ID (54=Python, 71=Java, 50=C++, etc)",
    )
    """Judge0 language identifier."""

    testcase_id: UUID | None = Field(
        None, description="Specific test case to run. If null, runs first test case."
    )
    """Optional test case. Runs first if not specified."""


class StudentTestCaseRunResultResponse(BaseModel):
    """Response with execution result for a test case.
    
    Contains all execution details: status, output, time, memory.
    
    Example:
        ```json
        {
            "testcase_id": "550e8400-e29b-41d4-a716-446655440000",
            "passed": true,
            "status_description": "Accepted",
            "time": 0.125,
            "memory": 12.5,
            "stdout": "output line 1\\noutput line 2",
            "stderr": null,
            "compile_output": null,
            "expected_output": "output line 1\\noutput line 2"
        }
        ```
    """

    testcase_id: UUID
    """Which test case this result is for."""

    passed: bool
    """True if test case passed (Accepted verdict)."""

    status_description: str = Field(..., description="Accepted, Wrong Answer, etc")
    """Human-readable status (Accepted, Wrong Answer, Time Limit Exceeded, Runtime Error, Compilation Error)."""

    time: float = Field(..., ge=0, description="Execution time in seconds")
    """Wall-clock execution time."""

    memory: float = Field(..., ge=0, description="Memory used in MB")
    """Peak memory consumed."""

    stdout: str | None = Field(None, description="Program output")
    """What the program printed to stdout."""

    stderr: str | None = Field(None, description="Error output if any")
    """What the program printed to stderr."""

    compile_output: str | None = Field(None, description="Compilation error if any")
    """Compilation error details."""

    expected_output: str | None = Field(None, description="What output was expected")
    """Expected output for debugging purposes."""

    model_config = ConfigDict(from_attributes=True)


class StudentCodeRunResponse(BaseModel):
    """Response to student code run request.
    
    Contains execution result for the requested test case.
    
    Example:
        ```json
        {
            "success": true,
            "message": "Test case executed successfully",
            "question_id": "550e8400-e29b-41d4-a716-446655440001",
            "result": {
                "testcase_id": "550e8400-e29b-41d4-a716-446655440002",
                "passed": true,
                "status_description": "Accepted",
                "time": 0.125,
                "memory": 12.5,
                "stdout": "output",
                "stderr": null,
                "compile_output": null,
                "expected_output": "output"
            }
        }
        ```
    """

    success: bool = Field(alias="passed")
    """Whether code execution completed without errors."""

    message: str
    """Status message."""

    question_id: UUID
    """Problem that was tested."""

    result: StudentTestCaseRunResultResponse
    """Execution result details."""

    model_config = ConfigDict(from_attributes=True)
