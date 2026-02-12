"""Add contest_id to team table - make teams contest-scoped

Revision ID: 001_contest_scoped_team
Revises: 75f8ef077d61
Create Date: 2026-02-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '001_contest_scoped_team'
down_revision: Union[str, Sequence[str], None] = '75f8ef077d61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add contest_id to team table."""
    # Step 1: Add column as nullable (safer approach - no risky default)
    op.add_column('team', sa.Column('contest_id', postgresql.UUID(as_uuid=True), nullable=True))
    
    # Step 2: Backfill existing team rows with actual contest IDs
    # Assign all existing teams to the first contest in the system
    op.execute("""
        UPDATE "team" SET contest_id = (SELECT id FROM contest LIMIT 1) 
        WHERE contest_id IS NULL
    """)
    
    # Step 3: Create the foreign key constraint (now safe because all values exist in contest table)
    op.create_foreign_key(
        'fk_team_contest_id',
        'team',
        'contest',
        ['contest_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Step 4: Make column NOT NULL after backfill succeeds
    op.alter_column('team', 'contest_id', nullable=False)


def downgrade() -> None:
    """Downgrade schema - remove contest_id from team table."""
    # Drop foreign key constraint
    op.drop_constraint('fk_team_contest_id', 'team', type_='foreignkey')
    
    # Drop column
    op.drop_column('team', 'contest_id')
