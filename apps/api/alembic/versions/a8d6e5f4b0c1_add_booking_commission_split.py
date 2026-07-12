"""add booking.commission_cents / commission_gst_cents (provider tax invoice, ADR-0002)

Revision ID: a8d6e5f4b0c1
Revises: f7c5d4e3a8b9
Create Date: 2026-07-12 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a8d6e5f4b0c1'
down_revision: str | None = 'f7c5d4e3a8b9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'booking',
        sa.Column('commission_cents', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'booking',
        sa.Column('commission_gst_cents', sa.Integer(), nullable=False, server_default='0'),
    )
    op.alter_column('booking', 'commission_cents', server_default=None)
    op.alter_column('booking', 'commission_gst_cents', server_default=None)


def downgrade() -> None:
    op.drop_column('booking', 'commission_gst_cents')
    op.drop_column('booking', 'commission_cents')
