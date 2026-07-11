"""Scheduler domain model (PRD §7.5 reminders).

``SessionReminder`` is the idempotency marker for pre-session reminder emails:
one row per (session, window) records that the batch has been sent, so the
worker can run every few minutes without ever re-sending. The ``UNIQUE`` is the
guarantee — not application timing.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class SessionReminder(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "session_reminder"
    __table_args__ = (
        # A given reminder window fires at most once per session.
        UniqueConstraint("session_id", "window", name="uq_session_reminder_window"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), index=True, nullable=False
    )
    window: Mapped[str] = mapped_column(String(8), nullable=False)  # '48h' | '3h'
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False)
