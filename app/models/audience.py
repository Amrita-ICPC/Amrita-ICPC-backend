"""Audience-related database models.

This module defines the audience entity and association tables that connect
audiences to users and contests.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.enums import AudienceType

if TYPE_CHECKING:
    from app.models.contest import Contest
    from app.models.user import User


class Audience(Base):
    """Represents a target audience.

    Attributes:
        id: Unique audience identifier.
        name: Unique audience name.
        description: Optional audience description.
    """

    __tablename__ = "audience"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(unique=True, nullable=False)
    audience_type: Mapped[AudienceType] = mapped_column(
        Enum(AudienceType, name="audiencetype"),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(nullable=True)

    user_links: Mapped[list["UserAudience"]] = relationship(
        "UserAudience",
        back_populates="audience",
        cascade="all, delete-orphan",
    )
    contest_links: Mapped[list["ContestAudience"]] = relationship(
        "ContestAudience",
        back_populates="audience",
        cascade="all, delete-orphan",
    )


class UserAudience(Base):
    """Association table linking users and audiences.

    Attributes:
        user_id: Related user identifier.
        audience_id: Related audience identifier.
        audience: Related audience object.
        user: Related user object.
    """

    __tablename__ = "user_audience"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    audience_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audience.id", ondelete="CASCADE"),
        primary_key=True,
    )

    audience: Mapped[Audience] = relationship(
        "Audience",
        back_populates="user_links",
    )
    user: Mapped[User] = relationship(
        "User",
        back_populates="audience_links",
    )


class ContestAudience(Base):
    """Association table linking contests and audiences.

    Attributes:
        contest_id: Related contest identifier.
        audience_id: Related audience identifier.
        audience: Related audience object.
        contest: Related contest object.
    """

    __tablename__ = "contest_audience"

    contest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contest.id", ondelete="CASCADE"),
        primary_key=True,
    )
    audience_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audience.id", ondelete="CASCADE"),
        primary_key=True,
    )

    audience: Mapped[Audience] = relationship(
        "Audience",
        back_populates="contest_links",
    )
    contest: Mapped[Contest] = relationship(
        "Contest",
        back_populates="audience_links",
    )
