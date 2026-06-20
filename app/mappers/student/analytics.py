"""Mapper functions for student-facing contest team analytics.

Maps the same raw rows used by the instructor-facing analytics (see
``app/mappers/team.py``) to the stripped-down, student-safe schemas in
``app/schema/student/analytics.py`` (no flagging details, no system_error
verdict counts, no source code).
"""

from typing import Any

from app.schema.student.analytics import (
    StudentMemberDetail,
    StudentMemberQuestionAnalytics,
    StudentMemberQuestionSubmissions,
    StudentQuestionStats,
    StudentSubmissionItem,
    StudentSubmissionStats,
    StudentSubmissionVerdictStats,
    StudentTeamAnalytics,
    StudentTeamMemberSummary,
)


def _row_int(row: Any, field: str) -> int:
    return int(getattr(row, field, 0) or 0)


def to_student_team_analytics(
    team_row: Any,
    member_rows: list[Any],
) -> StudentTeamAnalytics:
    """Map team analytics query rows to the student-facing schema."""
    members = [
        StudentTeamMemberSummary(
            user_id=member.id,
            contest_team_member_id=member.contest_team_member_id,
            name=member.name,
            email=member.email,
            is_leader=bool(member.is_leader),
            is_participated=bool(member.is_participated),
            score=_row_int(member, "score"),
            started_at=member.started_at,
            ended_at=member.ended_at,
        )
        for member in member_rows
    ]

    return StudentTeamAnalytics(
        contest_team_id=team_row.contest_team_id,
        name=team_row.name,
        score=_row_int(team_row, "score"),
        members=members,
        total_submissions=_row_int(team_row, "total_submissions"),
        accepted_submission=_row_int(team_row, "accepted_submission"),
        wrong_answer=_row_int(team_row, "wrong_answer"),
        time_limit_exceeded=_row_int(team_row, "time_limit_exceeded"),
        runtime_error=_row_int(team_row, "runtime_error"),
        compilation_error=_row_int(team_row, "compilation_error"),
        memory_limit_exceeded=_row_int(team_row, "memory_limit_exceeded"),
        pending_submission=_row_int(team_row, "pending_submission"),
    )


def to_student_member_detail(row: Any) -> StudentMemberDetail:
    """Map a contest-team member analytics row to the student-facing detail schema."""
    return StudentMemberDetail(
        contest_team_member_id=row.contest_team_member_id,
        user_id=row.user_id,
        name=row.name,
        email=row.email,
        is_leader=bool(row.is_leader),
        is_participated=bool(row.is_participated),
        score=_row_int(row, "score"),
        started_at=row.started_at,
        ended_at=row.ended_at,
        submission_statistics=StudentSubmissionStats(
            total=_row_int(row, "total"),
            accepted=_row_int(row, "accepted"),
            wrong_answer=_row_int(row, "wrong_answer"),
            time_limit_exceeded=_row_int(row, "time_limit_exceeded"),
            runtime_error=_row_int(row, "runtime_error"),
            memory_limit_exceeded=_row_int(row, "memory_limit_exceeded"),
            compilation_error=_row_int(row, "compilation_error"),
            pending=_row_int(row, "pending"),
        ),
        question_statistics=StudentQuestionStats(
            attempted=_row_int(row, "attempted"),
            solved=_row_int(row, "solved"),
            unsolved=_row_int(row, "unsolved"),
        ),
    )


def to_student_member_question_analytics(
    question_rows: list[Any],
) -> list[StudentMemberQuestionAnalytics]:
    """Map contest-team member question analytics rows to the student-facing schema."""
    return [
        StudentMemberQuestionAnalytics(
            question_id=row.question_id,
            title=row.title,
            difficulty=row.difficulty,
            time_limit_ms=row.time_limit_ms,
            memory_limit_mb=row.memory_limit_mb,
            total_submission=_row_int(row, "total_submission"),
            accepted_submission=_row_int(row, "accepted_submission"),
        )
        for row in question_rows
    ]


def to_student_member_question_submissions(
    question_row: Any,
    statistics_row: Any,
    submission_rows: list[Any],
) -> StudentMemberQuestionSubmissions:
    """Map question submission drilldown rows to the student-facing schema."""
    return StudentMemberQuestionSubmissions(
        question_id=question_row.question_id,
        question_title=question_row.question_title,
        statistics=StudentSubmissionVerdictStats(
            total=_row_int(statistics_row, "total"),
            accepted=_row_int(statistics_row, "accepted"),
            wrong_answer=_row_int(statistics_row, "wrong_answer"),
            time_limit_exceeded=_row_int(statistics_row, "time_limit_exceeded"),
            runtime_error=_row_int(statistics_row, "runtime_error"),
            compilation_error=_row_int(statistics_row, "compilation_error"),
        ),
        submissions=[
            StudentSubmissionItem(
                submission_id=row.submission_id,
                status=row.status,
                score=_row_int(row, "score"),
                language=row.language,
                created_at=row.created_at,
                execution_time_ms=row.execution_time,
                memory_kb=row.memory,
            )
            for row in submission_rows
        ],
    )
