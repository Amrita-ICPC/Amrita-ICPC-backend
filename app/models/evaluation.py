from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.contest import Contest
    from app.models.user import User


class Evaluation(Base):
    __tablename__ = "evaluation"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), nullable=False
    )

    is_evaluated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    total_submissions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_submissions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    contest: Mapped[Contest] = relationship("Contest")
    creator: Mapped[User] = relationship("User")
