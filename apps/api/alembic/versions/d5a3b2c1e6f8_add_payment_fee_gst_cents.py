"""add payment.fee_gst_cents (GST on the platform commission, ADR-0002)

Revision ID: d5a3b2c1e6f8
Revises: c4e2d1f0a6b7
Create Date: 2026-07-12 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd5a3b2c1e6f8'
down_revision: str | None = 'c4e2d1f0a6b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'payment',
        sa.Column(
            'fee_gst_cents', sa.Integer(), nullable=False, server_default='0'
        ),
    )
    # The ORM supplies the default on insert; drop the server default to keep the schema clean.
    op.alter_column('payment', 'fee_gst_cents', server_default=None)
    op.create_check_constraint(
        'ck_payment_fee_gst_nonneg', 'payment', 'fee_gst_cents >= 0'
    )


def downgrade() -> None:
    op.drop_constraint('ck_payment_fee_gst_nonneg', 'payment', type_='check')
    op.drop_column('payment', 'fee_gst_cents')
