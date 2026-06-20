from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import QuestionDifficulty, SubmissionStatus

# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------


class StudentSubmissionStats(BaseModel):
    """Verdict breakdown for a set of submissions (student-visible verdicts only)."""

    total: int = Field(0, description="Total number of submissions")
    accepted: int = Field(0, description="Accepted (AC)")
    wrong_answer: int = Field(0, description="Wrong answer (WA)")
    time_limit_exceeded: int = Field(0, description="Time limit exceeded (TLE)")
    runtime_error: int = Field(0, description="Runtime error (RE)")
    memory_limit_exceeded: int = Field(0, description="Memory limit exceeded (MLE)")
    compilation_error: int = Field(0, description="Compilation error (CE)")
    pending: int = Field(0, description="Pending / in-queue submissions")

    model_config = ConfigDict(from_attributes=True)


class StudentQuestionStats(BaseModel):
    """Per-member question-level summary (attempted / solved counts)."""

    attempted: int = Field(0, description="Number of questions attempted")
    solved: int = Field(0, description="Number of questions solved (at least one AC)")
    unsolved: int = Field(0, description="Attempted questions not yet solved")

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Route 1 – Team analytics
# GET /student/contests/{contest_id}/my-team/analytics
# ---------------------------------------------------------------------------


class StudentTeamMemberSummary(BaseModel):
    """Lightweight member row inside the team analytics response.

    Flagging fields are intentionally excluded — they are instructor-only.
    """

    user_id: UUID = Field(..., description="User ID of the member")
    contest_team_member_id: UUID = Field(..., description="ContestTeamMember record ID")
    name: str = Field(..., description="Full name of the member")
    email: str = Field(..., description="Email address of the member")
    is_leader: bool = Field(False, description="Whether this member is the team leader")
    is_participated: bool = Field(
        False, description="Whether the member has started the contest session"
    )
    score: int = Field(0, description="Member's accumulated score")
    started_at: Optional[datetime] = Field(
        None, description="Timestamp when the member started the contest"
    )
    ended_at: Optional[datetime] = Field(
        None, description="Timestamp when the member's session ended"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentTeamAnalytics(BaseModel):
    """Team-level analytics visible to all accepted members of the team.

    Instructor-only fields stripped:
      - Member flagging details
      - system_error verdict counts
    """

    contest_team_id: UUID = Field(..., description="Contest team identifier")
    name: str = Field(..., description="Team name")
    score: int = Field(0, description="Aggregated team score")
    members: list[StudentTeamMemberSummary] = Field(
        default_factory=list,
        description="Summary rows for each accepted team member",
    )

    # Submission verdict breakdown (no system_error for students)
    total_submissions: int = Field(0, description="Total submissions by the team")
    accepted_submission: int = Field(0, description="Accepted submissions")
    wrong_answer: int = Field(0, description="Wrong answer submissions")
    time_limit_exceeded: int = Field(0, description="Time limit exceeded submissions")
    runtime_error: int = Field(0, description="Runtime error submissions")
    compilation_error: int = Field(0, description="Compilation error submissions")
    memory_limit_exceeded: int = Field(
        0, description="Memory limit exceeded submissions"
    )
    pending_submission: int = Field(0, description="Submissions still being judged")

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Route 2 – Member detail
# GET /student/contests/{contest_id}/my-team/members/{contest_team_member_id}
# ---------------------------------------------------------------------------


class StudentMemberDetail(BaseModel):
    """Detailed analytics for a single team member, student-safe.

    Stripped vs instructor's ContestTeamMemberDetail:
      - is_flagged, flagged_at, flagged_reason
      - extra_time_seconds, remaining_time_seconds, base_end_time
      - system_error in submission_statistics
    """

    contest_team_member_id: UUID = Field(..., description="ContestTeamMember record ID")
    user_id: UUID = Field(..., description="User ID of the member")
    name: str = Field(..., description="Full name of the member")
    email: str = Field(..., description="Email address of the member")
    is_leader: bool = Field(False, description="Whether this member is the team leader")
    is_participated: bool = Field(
        False, description="Whether the member has started the contest session"
    )
    score: int = Field(0, description="Member's accumulated score")
    started_at: Optional[datetime] = Field(None, description="Session start timestamp")
    ended_at: Optional[datetime] = Field(None, description="Session end timestamp")

    submission_statistics: StudentSubmissionStats = Field(
        default_factory=StudentSubmissionStats,
        description="Verdict breakdown for all submissions by this member",
    )
    question_statistics: StudentQuestionStats = Field(
        default_factory=StudentQuestionStats,
        description="Question-level attempt and solve counts for this member",
    )

    model_config = ConfigDict(from_attributes=True)


class StudentMemberQuestionAnalytics(BaseModel):
    """Per-question analytics row for a single member.

    Equivalent to ContestTeamMemberQuestionAnalytics (instructor) —
    no fields removed here since question metadata is not sensitive.
    """

    question_id: UUID = Field(..., description="Question identifier")
    title: str = Field(..., description="Question title")
    difficulty: QuestionDifficulty = Field(..., description="Question difficulty level")
    time_limit_ms: int = Field(..., description="Time limit in milliseconds")
    memory_limit_mb: int = Field(..., description="Memory limit in megabytes")
    total_submission: int = Field(
        0, description="Total submissions by this member for this question"
    )
    accepted_submission: int = Field(
        0, description="Accepted submissions by this member for this question"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentSubmissionItem(BaseModel):
    """A single submission row in the student-facing list.

    Stripped vs instructor's ContestTeamMemberQuestionSubmissionItem:
      - No source_code field
    Stripped vs SubmissionDetailResponse (instructor):
      - No source_code, no testcase I/O, no submitted_by user detail
        (student already knows whose submissions these are by route context)
    """

    submission_id: UUID = Field(..., description="Unique submission identifier")
    status: Optional[SubmissionStatus] = Field(
        None, description="Verdict for this submission"
    )
    score: int = Field(0, description="Score awarded for this submission")
    language: str = Field(..., description="Programming language name used")
    created_at: datetime = Field(..., description="Submission timestamp (UTC)")
    execution_time_ms: Optional[int] = Field(
        None, description="Execution time in milliseconds"
    )
    memory_kb: Optional[int] = Field(None, description="Memory used in kilobytes")
    passed_testcases: int = Field(0, description="Number of testcases passed")
    total_testcases: int = Field(0, description="Total testcases evaluated")

    model_config = ConfigDict(from_attributes=True)


class StudentSubmissionVerdictStats(BaseModel):
    """Verdict aggregation for a single question's submissions by one member."""

    total: int = Field(0, description="Total submissions for this question")
    accepted: int = Field(0, description="Accepted submissions")
    wrong_answer: int = Field(0, description="Wrong answer submissions")
    time_limit_exceeded: int = Field(0, description="Time limit exceeded submissions")
    runtime_error: int = Field(0, description="Runtime error submissions")
    compilation_error: int = Field(0, description="Compilation error submissions")
    memory_limit_exceeded: int = Field(
        0, description="Memory limit exceeded submissions"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentMemberQuestionSubmissions(BaseModel):
    """All submissions by one member for one question, student-safe.

    Equivalent to ContestTeamMemberQuestionSubmissions (instructor) but:
      - No source code in individual submission items
      - No testcase input/output data
      - system_error excluded from stats
    """

    question_id: UUID = Field(..., description="Question identifier")
    question_title: str = Field(..., description="Question title")
    statistics: StudentSubmissionVerdictStats = Field(
        default_factory=StudentSubmissionVerdictStats,
        description="Aggregate verdict breakdown for this question",
    )
    submissions: list[StudentSubmissionItem] = Field(
        default_factory=list,
        description="Individual submission records, newest first",
    )

    model_config = ConfigDict(from_attributes=True)
