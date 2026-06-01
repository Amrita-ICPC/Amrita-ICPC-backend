from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum

from app.utils.enums import InvitationType, TeamInvitationStatus

if TYPE_CHECKING:
    from app.models.user import User

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Team(Base):
    __tablename__ = "team"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    logo: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    leader_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)

    audience_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audience.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    creator = relationship("User", foreign_keys=[created_by])
    leader = relationship("User", foreign_keys=[leader_id])
    audience = relationship("Audience")
    members: Mapped[list[TeamUser]] = relationship("TeamUser", back_populates="team")
    team_contests = relationship("ContestTeam", back_populates="team")
    contest_violations = relationship(
        "ContestTeamViolation", back_populates="team", cascade="all, delete-orphan"
    )
    invitations: Mapped[list[TeamInvitation]] = relationship(
        "TeamInvitation", back_populates="team", cascade="all, delete-orphan"
    )


class TeamUser(Base):
    __tablename__ = "team_user"

    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="teams")


class TeamInvitation(Base):
    __tablename__ = "team_invitation"
    __table_args__ = (
        CheckConstraint(
            """
            (
                invitation_type = 'INVITE'
                AND reciever_id IS NOT NULL
            )
            OR
            (
                invitation_type = 'REQUEST'
                AND reciever_id IS NULL
            )
            """,
            name="ck_team_invitation_receiver_logic",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), nullable=False
    )

    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    reciever_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )

    invitation_type: Mapped[InvitationType] = mapped_column(
        Enum(InvitationType, native_enum=False),
        default=InvitationType.INVITE,
    )

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[TeamInvitationStatus] = mapped_column(
        Enum(TeamInvitationStatus, native_enum=False),
        default=TeamInvitationStatus.PENDING,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    team: Mapped["Team"] = relationship("Team", back_populates="invitations")
    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id])
    reciever: Mapped["User"] = relationship("User", foreign_keys=[reciever_id])
