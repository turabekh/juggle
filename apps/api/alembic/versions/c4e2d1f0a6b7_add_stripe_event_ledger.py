"""add stripe_event webhook idempotency ledger

Revision ID: c4e2d1f0a6b7
Revises: b3f1c0a2d4e5
Create Date: 2026-07-11 12:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4e2d1f0a6b7'
down_revision: str | None = 'b3f1c0a2d4e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'stripe_event',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=80), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', name='uq_stripe_event_event_id'),
    )


def downgrade() -> None:
    op.drop_table('stripe_event')
