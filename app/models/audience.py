import uuid

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Audience(Base):
    __tablename__ = "audience"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)


class UserAudience(Base):
    __tablename__ = "user_audience"

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    audience_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    audience = relationship("Audience", back_populates="audience")
    user = relationship("User", back_populates="audience")


class ContestAudience(Base):
    __tablename__ = "contest_audience"

    contest_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    audience_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    audience = relationship("Audience", back_populates="contest_audience")
    contest = relationship("Contest", back_populates="contest_audience")
