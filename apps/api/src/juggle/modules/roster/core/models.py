"""Roster domain models (PRD §8.3): morning-of attendance check-in.

The roster itself is a read view over confirmed bookings; ``Attendance`` is the
one piece of state it owns — whether a child on a session has been checked in.
It is keyed by ``booking_child_id`` (one child on one booking), so a child booked
on two sessions is checked in independently for each.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class Attendance(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "attendance"
    __table_args__ = (
        # One check-in record per child-on-a-booking.
        UniqueConstraint("booking_child_id", name="uq_attendance_booking_child"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), index=True, nullable=False
    )
    booking_child_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("booking_child.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Non-null == checked in at this time; null == not yet arrived.
    attended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    marked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
