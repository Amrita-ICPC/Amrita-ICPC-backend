"""Schemas for code execution via Judge0."""

from typing import Optional

from pydantic import BaseModel, Field


# LANGUAGES
class Language(BaseModel):
    """Supported programming language details from Judge0."""

    id: int = Field(..., description="Judge0 language ID")
    name: str = Field(..., description="Language name (e.g., 'Python 3.11')")


# RUN (Practice) SCHEMAS - For running code against test cases

class CodeRunRequest(BaseModel):
    """Request to run code against test cases (practice/feedback).
    
    Stdin and expected outputs are fetched from non-hidden test cases.
    User only provides code and language.
    """

    question_id: str = Field(..., description="Question UUID to run code against")
    source_code: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="The source code to execute",
    )
    language_id: int = Field(..., gt=0, description="Judge0 language ID (e.g., 71 for Python)")


class TestCaseRunResult(BaseModel):
    """Result of running code against a single test case.
    
    Only returned when code compiles successfully.
    If compilation fails, use CompilationErrorResponse instead.
    """

    testcase_id: str = Field(..., description="Test case UUID")
    status: str = Field(
        ...,
        description="Execution status (ACCEPTED, WRONG_ANSWER, RUNTIME_ERROR, TIME_LIMIT_EXCEEDED, SYSTEM_ERROR)",
    )
    passed: bool = Field(
        ..., description="Whether this test case passed (output matches expected)"
    )
    stdout: Optional[str] = Field(
        default=None, description="Actual output from user's code"
    )
    stderr: Optional[str] = Field(
        default=None, description="Runtime error output (e.g., ZeroDivisionError, IndexError)"
    )
    expected_output: Optional[str] = Field(
        default=None, description="Expected output from test case"
    )
    time: Optional[float] = Field(
        default=None, description="Execution time in seconds"
    )
    memory: Optional[int] = Field(
        default=None, description="Memory used in kilobytes"
    )


class CodeRunResponse(BaseModel):
    """Response with test case run results (no database record)."""

    testcases: list[TestCaseRunResult] = Field(
        ..., description="Results for each test case executed"
    )
    total: int = Field(..., description="Total number of tests executed")
    passed: int = Field(..., description="Number of tests passed")

    class Config:
        json_schema_extra = {
            "example": {
                "testcases": [
                    {
                        "testcase_id": "tc_1",
                        "status": "PASSED",
                        "stdout": "120",
                        "expected_output": "120",
                        "passed": True,
                        "time": 5,
                        "memory": 10,
                    },
                    {
                        "testcase_id": "tc_2",
                        "status": "FAILED",
                        "stdout": "240",
                        "expected_output": "120",
                        "stderr": None,
                        "passed": False,
                        "time": 8,
                        "memory": 15,
                    },
                ],
                "total": 2,
                "passed": 1,
            }
        }


# ERROR SCHEMAS
class CompilationErrorResponse(BaseModel):
    """Response when code fails to compile.
    
    When code has syntax/import errors, test case execution is skipped.
    This is returned instead of CodeRunResponse.
    """

    error_code: str = Field(
        default="COMPILATION_ERROR",
        description="Error code: always 'COMPILATION_ERROR'",
    )
    compile_output: str = Field(
        ..., description="Compilation error details (syntax error, import error, etc.)"
    )
    message: str = Field(
        default="Code has compilation errors",
        description="Human-readable error message",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "error_code": "COMPILATION_ERROR",
                "compile_output": "SyntaxError: invalid syntax (<string>, line 5)",
                "message": "Code has compilation errors",
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response for code run failures.
    
    Used for API-level errors (question not found, language not supported, etc.).
    NOT for code execution errors (use CompilationErrorResponse for compilation errors).
    """

    error_code: str = Field(
        ..., description="Error code (e.g., 'QUESTION_NOT_FOUND', 'INVALID_LANGUAGE')"
    )
    message: str = Field(..., description="Human-readable error message")
    details: Optional[str] = Field(
        default=None, description="Additional error details for debugging"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "error_code": "QUESTION_NOT_FOUND",
                    "message": "Question with ID 'q_abc123' not found",
                    "details": None,
                },
                {
                    "error_code": "LANGUAGE_NOT_SUPPORTED",
                    "message": "Question does not support language ID 71 (Python)",
                    "details": "Supported languages are: Java (62), C++ (54)",
                },
                {
                    "error_code": "INVALID_LANGUAGE",
                    "message": "Language ID 999 not found in Judge0",
                    "details": None,
                },
                {
                    "error_code": "INVALID_SOURCE_CODE",
                    "message": "Source code exceeds 50KB maximum size limit",
                    "details": None,
                },
                {
                    "error_code": "JUDGE0_ERROR",
                    "message": "Judge0 service temporarily unavailable",
                    "details": "Failed to submit code to Judge0: HTTP 503",
                },
                {
                    "error_code": "EXECUTION_ERROR",
                    "message": "Code execution failed",
                    "details": "Compilation Error: Syntax error on line 5",
                },
            ]
        }