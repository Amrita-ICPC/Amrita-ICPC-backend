"""add uq_contest_active_student index

Revision ID: 00f1cba091ac
Revises: 82251db306e2
Create Date: 2026-09-19 16:35:22.415322

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "00f1cba091ac"
down_revision: Union[str, Sequence[str], None] = "82251db306e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "uq_contest_active_student",
        "contest_team_member",
        ["contest_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('ACCEPTED')"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_contest_active_student",
        table_name="contest_team_member",
        postgresql_where=sa.text("status IN ('ACCEPTED')"),
    )
