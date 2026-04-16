"""Student-facing contest exceptions.

Re-exports contest exceptions with student-specific context.
"""

from app.exceptions.contest import ContestNotFoundError

__all__ = [
    "ContestNotFoundError",
]
