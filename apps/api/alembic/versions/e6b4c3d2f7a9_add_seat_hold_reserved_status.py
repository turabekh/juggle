"""add 'reserved' to seat_hold_status (firm checkout reservation, ADR-0005)

Revision ID: e6b4c3d2f7a9
Revises: d5a3b2c1e6f8
Create Date: 2026-07-12 09:10:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = 'e6b4c3d2f7a9'
down_revision: str | None = 'd5a3b2c1e6f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PG 16 allows ADD VALUE inside a transaction; the value is only used by later txns.
    op.execute("ALTER TYPE seat_hold_status ADD VALUE IF NOT EXISTS 'reserved'")


def downgrade() -> None:
    # Postgres cannot drop an enum value; leaving 'reserved' in place is harmless.
    pass
