import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
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
    tags = relationship("QuestionTag", back_populates="question")
    testcases = relationship(
        "TestCase", back_populates="question", cascade="all, delete-orphan"
    )
    languages = relationship(
        "QuestionLanguage", back_populates="question", cascade="all, delete-orphan"
    )
    templates = relationship(
        "QuestionTemplate", back_populates="question", cascade="all, delete-orphan"
    )


class QuestionTemplate(Base):
    __tablename__ = "question_template"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    question_id = mapped_column(ForeignKey("question.id"), nullable=False)

    language_id = mapped_column(ForeignKey("language.id"), nullable=False)

    # what user sees initially
    starter_code = mapped_column(Text, nullable=False)

    # optional: hidden wrapper for execution (VERY powerful)
    # e.g., wrapping function into main()
    driver_code = mapped_column(Text)

    # optional: full solution template for editorial/testing
    solution_code = mapped_column(Text)

    question = relationship("Question", back_populates="templates")
    language = relationship("Language", back_populates="question_template_mappings")


class TestCase(Base):
    __tablename__ = "testcase"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    question_id = mapped_column(ForeignKey("question.id"))

    input = mapped_column(Text, nullable=False)
    output = mapped_column(Text, nullable=False)

    is_hidden = mapped_column(Boolean, default=True)
    weight = mapped_column(Integer, default=1)  # for scoring

    order = mapped_column(Integer, nullable=False)

    question = relationship("Question", back_populates="testcases")

    created_at = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    created_by = mapped_column(ForeignKey("users.id"))


class QuestionLanguage(Base):
    __tablename__ = "question_language"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    question_id = mapped_column(ForeignKey("question.id"))
    language_id = mapped_column(ForeignKey("language.id"), nullable=False)

    question = relationship("Question", back_populates="languages")
    language = relationship("Language", back_populates="question_language_mappings")


class Submission(Base):
    __tablename__ = "submission"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = mapped_column(ForeignKey("users.id"))
    question_id = mapped_column(ForeignKey("question.id"))

    source_code = mapped_column(Text, nullable=False)
    language_id = mapped_column(ForeignKey("language.id"), nullable=False)

    status = mapped_column(SUBMISSION_STATUS_ENUM, default=SubmissionStatus.QUEUED)

    score = mapped_column(Integer, default=0)
    passed_testcases = mapped_column(Integer, default=0)
    total_testcases = mapped_column(Integer, default=0)

    total_time = mapped_column(Integer)
    total_memory = mapped_column(Integer)

    created_at = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    testcases = relationship(
        "SubmissionTestCase", back_populates="submission", cascade="all, delete-orphan"
    )
    language = relationship("Language", back_populates="submissions")


class SubmissionTestCase(Base):
    __tablename__ = "submission_testcase"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    submission_id = mapped_column(ForeignKey("submission.id"))
    testcase_id = mapped_column(ForeignKey("testcase.id"))

    status = mapped_column(SUBMISSION_STATUS_ENUM, nullable=False)
    stdout = mapped_column(Text)
    stderr = mapped_column(Text)

    time = mapped_column(Integer)
    memory = mapped_column(Integer)

    submission = relationship("Submission", back_populates="testcases")
