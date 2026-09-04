"""add contest_audience indexes

Revision ID: d5b162c13f80
Revises:
Create Date: 2026-09-04 21:47:04.243877

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5b162c13f80"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_contest_audience_audience_id_contest_id",
        "contest_audience",
        ["audience_id", "contest_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_contest_audience_audience_id_contest_id",
        table_name="contest_audience",
    )
