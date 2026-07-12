"""payout clawback ledger: booking.accrued_net_cents/payout_id + payment.refunded_cents

Revision ID: f7c5d4e3a8b9
Revises: e6b4c3d2f7a9
Create Date: 2026-07-12 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f7c5d4e3a8b9'
down_revision: str | None = 'e6b4c3d2f7a9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'booking',
        sa.Column('accrued_net_cents', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'booking',
        sa.Column('payout_id', sa.Uuid(), nullable=True),
    )
    op.create_index('ix_booking_payout_id', 'booking', ['payout_id'])
    op.create_foreign_key(
        'fk_booking_payout_id', 'booking', 'payout', ['payout_id'], ['id'], ondelete='SET NULL'
    )
    op.add_column(
        'payment',
        sa.Column('refunded_cents', sa.Integer(), nullable=False, server_default='0'),
    )
    # ORM supplies defaults on insert; drop server defaults to keep the schema clean.
    op.alter_column('booking', 'accrued_net_cents', server_default=None)
    op.alter_column('payment', 'refunded_cents', server_default=None)


def downgrade() -> None:
    op.drop_column('payment', 'refunded_cents')
    op.drop_constraint('fk_booking_payout_id', 'booking', type_='foreignkey')
    op.drop_index('ix_booking_payout_id', table_name='booking')
    op.drop_column('booking', 'payout_id')
    op.drop_column('booking', 'accrued_net_cents')
