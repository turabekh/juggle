"""add org stripe connect flags (charges_enabled, payouts_enabled)

Revision ID: b3f1c0a2d4e5
Revises: 8b9699333869
Create Date: 2026-07-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b3f1c0a2d4e5'
down_revision: str | None = '8b9699333869'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'organisation',
        sa.Column(
            'charges_enabled', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        'organisation',
        sa.Column(
            'payouts_enabled', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    # The ORM supplies the default on insert; drop the server default to keep the schema clean.
    op.alter_column('organisation', 'charges_enabled', server_default=None)
    op.alter_column('organisation', 'payouts_enabled', server_default=None)


def downgrade() -> None:
    op.drop_column('organisation', 'payouts_enabled')
    op.drop_column('organisation', 'charges_enabled')
