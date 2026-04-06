from sqlalchemy import Integer, Text
from sqlalchemy.orm import mapped_column, relationship

from app.models.base import Base


class Language(Base):
    __tablename__ = "language"

    id = mapped_column(Integer, primary_key=True)  # use judge0 id directly

    name = mapped_column(Text, nullable=False)  # "Python 3"
    slug = mapped_column(Text, unique=True, nullable=False)  # "python"

    # optional (very useful later)
    file_extension = mapped_column(Text)  # ".py"
    monaco_language = mapped_column(Text)  # "python"

    question_language_mappings = relationship(
        "QuestionLanguage", back_populates="language"
    )
    question_template_mappings = relationship(
        "QuestionTemplate", back_populates="language"
    )
    submissions = relationship("Submission", back_populates="language")
