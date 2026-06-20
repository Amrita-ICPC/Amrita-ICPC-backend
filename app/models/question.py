import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.language import Language
from app.utils.enums import QuestionDifficulty, SubmissionStatus

SUBMISSION_STATUS_ENUM = Enum(
    SubmissionStatus,
    name="submissionstatus",
    metadata=Base.metadata,
)


class Question(Base):
    __tablename__ = "question"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[QuestionDifficulty] = mapped_column(
        Enum(QuestionDifficulty), nullable=False
    )

    time_limit_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    banks = relationship("BankQuestion", back_populates="question")
    contests = relationship("ContestQuestion", back_populates="question")
    tags = relationship(
        "QuestionTag",
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    testcases = relationship(
        "TestCase",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="TestCase.order",
    )
    languages = relationship(
        "QuestionLanguage", back_populates="question", cascade="all, delete-orphan"
    )
    templates = relationship(
        "QuestionTemplate", back_populates="question", cascade="all, delete-orphan"
    )


class QuestionTemplate(Base):
    __tablename__ = "question_template"
    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "language_id",
            name="uq_question_template_per_question",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), nullable=False
    )

    language_id: Mapped[int] = mapped_column(ForeignKey("language.id"), nullable=False)

    # what user sees initially
    starter_code: Mapped[str] = mapped_column(Text, nullable=False)

    # optional: hidden wrapper for execution (VERY powerful)
    # e.g., wrapping function into main()
    driver_code: Mapped[str | None] = mapped_column(Text)

    # optional: full solution template for editorial/testing
    solution_code: Mapped[str | None] = mapped_column(Text)

    question: Mapped[Question] = relationship("Question", back_populates="templates")
    language: Mapped[Language] = relationship(
        "Language", back_populates="question_template_mappings"
    )


class TestCase(Base):
    __tablename__ = "testcase"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), nullable=False
    )

    input: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False)

    is_hidden: Mapped[bool] = mapped_column(Boolean, default=True)
    weight: Mapped[int] = mapped_column(Integer, default=1)  # for scoring

    order: Mapped[int] = mapped_column(Integer, nullable=False)

    question: Mapped[Question] = relationship("Question", back_populates="testcases")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )


class QuestionLanguage(Base):
    __tablename__ = "question_language"

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), primary_key=True
    )
    language_id: Mapped[int] = mapped_column(
        ForeignKey("language.id"), primary_key=True
    )

    question: Mapped[Question] = relationship("Question", back_populates="languages")
    language: Mapped[Language] = relationship(
        "Language", back_populates="question_language_mappings"
    )


class Submission(Base):
    __tablename__ = "submission"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), nullable=False
    )

    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    language_id: Mapped[int] = mapped_column(ForeignKey("language.id"), nullable=False)

    is_evaluated: Mapped[bool] = mapped_column(Boolean, default=False)

    score: Mapped[int] = mapped_column(Integer, default=0)

    total_time: Mapped[int | None] = mapped_column(Integer)
    total_memory: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Terminal fact: when the submission reached its final verdict.
    # Transient lifecycle (queued/running) is NOT persisted here; it lives in Redis.
    evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    testcases: Mapped[list["SubmissionTestCase"]] = relationship(
        "SubmissionTestCase", back_populates="submission", cascade="all, delete-orphan"
    )
    language: Mapped[Language] = relationship("Language", back_populates="submissions")
    question: Mapped[Question] = relationship("Question")
    contest_submission = relationship(
        "ContestSubmission",
        back_populates="submission",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def status(self) -> SubmissionStatus | None:
        if not self.is_evaluated:
            return None
        if not self.testcases:
            return SubmissionStatus.SYSTEM_ERROR
        for tc in self.testcases:
            if tc.status != SubmissionStatus.AC:
                return tc.status
        return SubmissionStatus.AC

    @property
    def passed_testcases(self) -> int:
        if hasattr(self, "_passed_testcases"):
            return self._passed_testcases
        if not self.is_evaluated or not self.testcases:
            return 0
        return sum(1 for tc in self.testcases if tc.status == SubmissionStatus.AC)

    @passed_testcases.setter
    def passed_testcases(self, value: int) -> None:
        self._passed_testcases = value

    @property
    def total_testcases(self) -> int:
        if hasattr(self, "_total_testcases"):
            return self._total_testcases
        if self.is_evaluated:
            return len(self.testcases)
        try:
            return len(self.question.testcases)
        except Exception:
            return 0

    @total_testcases.setter
    def total_testcases(self, value: int) -> None:
        self._total_testcases = value


class SubmissionTestCase(Base):
    __tablename__ = "submission_testcase"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submission.id", ondelete="CASCADE"), nullable=False
    )
    testcase_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("testcase.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[SubmissionStatus | None] = mapped_column(
        SUBMISSION_STATUS_ENUM, nullable=True
    )

    # Durable Judge0 token for this testcase execution. Persisted alongside the
    # result so completed submissions retain an audit trail / recovery handle.
    judge0_token: Mapped[str | None] = mapped_column(String(64), nullable=True)

    stdout: Mapped[str | None] = mapped_column(Text)
    stderr: Mapped[str | None] = mapped_column(Text)

    time: Mapped[int | None] = mapped_column(Integer)
    memory: Mapped[int | None] = mapped_column(Integer)

    submission: Mapped[Submission] = relationship(
        "Submission", back_populates="testcases"
    )
