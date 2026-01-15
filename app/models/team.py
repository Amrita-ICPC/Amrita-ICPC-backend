import uuid
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class Team(Base):
    __tablename__ = "team"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    logo: Mapped[str | None] = mapped_column(Text)

    members = relationship("TeamUser", back_populates="team")
    contests = relationship("ContestTeam", back_populates="team")

class TeamUser(Base):
    __tablename__ = "team_user"

    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="teams")
