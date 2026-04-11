"""Schemas for code execution via Judge0."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# JUDGE0 API RESPONSE MODELS (Internal DTOs)
class Judge0Language(BaseModel):
    """Type-safe Judge0 language API response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class Judge0SubmissionResponse(BaseModel):
    """Type-safe Judge0 submission API response."""

    model_config = ConfigDict(from_attributes=True)

    token: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    compile_output: Optional[str] = None
    status_id: Optional[int] = None
    time: Optional[str] = None
    memory: Optional[int] = None


# APPLICATION SCHEMAS (External API Models)
class Language(BaseModel):
    """Supported programming language details from Judge0."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Judge0 language ID")
    name: str = Field(..., description="Language name (e.g., 'Python 3.11')")


class CodeRunAsyncRequest(BaseModel):
    """Async code submission request with strict validation."""

    source_code: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="The source code to execute",
    )
    language_id: int = Field(..., gt=0, description="Judge0 language ID")
    stdin: Optional[str] = Field(
        default="",
        max_length=10000,
        description="Standard input for the program",
    )


class TokenResponse(BaseModel):
    """Response containing the submission token for polling."""

    token: str = Field(..., description="Submission token for status polling")


class ExecutionResultResponse(BaseModel):
    """Code execution result from Judge0."""

    model_config = ConfigDict(from_attributes=True)

    status_id: int = Field(
        ..., description="Judge0 status ID (1=Queue, 2=Processing, 3=Accepted, etc.)"
    )
    status_description: str = Field(
        ..., description="Human-readable status description"
    )

    stdout: Optional[str] = Field(
        default=None, description="Program standard output"
    )
    stderr: Optional[str] = Field(
        default=None, description="Program standard error output"
    )
    compile_output: Optional[str] = Field(
        default=None, description="Compilation error/warning output"
    )

    time: Optional[str] = Field(
        default=None, description="Execution time in seconds"
    )
    memory: Optional[int] = Field(
        default=None, description="Memory used in kilobytes"
    )