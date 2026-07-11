"""Waitlist domain model (PRD §7.7).

A ``WaitlistEntry`` is one guardian's place in the queue for a sold-out session.
When a seat frees up, reconciliation moves the front entry to ``offered`` and
reserves the seat with a claim-window seat hold (``offer_hold_id``); the guardian
claims by checking out against that hold. If the window lapses the offer expires
and the seat passes to the next family.

A guardian may hold only one *active* (waiting/offered) entry per session — a
partial unique index enforces that at the DB layer, while still allowing a fresh
entry after a previous one expired or was cancelled.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class WaitlistStatus(enum.StrEnum):
    waiting = "waiting"      # in the queue
    offered = "offered"      # a seat is held for them until offer_expires_at
    claimed = "claimed"      # they booked the offered seat
    expired = "expired"      # the claim window lapsed
    cancelled = "cancelled"  # they left the waitlist


ACTIVE_STATUSES = (WaitlistStatus.waiting, WaitlistStatus.offered)


class WaitlistEntry(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "waitlist_entry"
    __table_args__ = (
        # One active place per guardian per session (waiting or offered).
        Index(
            "uq_waitlist_active",
            "session_id",
            "guardian_id",
            unique=True,
            postgresql_where=text("status IN ('waiting', 'offered')"),
        ),
        # FIFO scan: front of the queue is the lowest seq for the session.
        Index("ix_waitlist_session_status_seq", "session_id", "status", "seq"),
    )

    # Monotonic insertion order for FIFO. A DB identity sequence advances per
    # INSERT even inside one transaction, so ordering is stable regardless of
    # `created_at` (which is the transaction clock and can tie).
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), index=True, nullable=False
    )
    guardian_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[WaitlistStatus] = mapped_column(
        Enum(WaitlistStatus, name="waitlist_status"),
        default=WaitlistStatus.waiting,
        nullable=False,
    )
    # Set while offered: the seat hold reserving their seat + the claim deadline.
    offer_hold_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seat_hold.id", ondelete="SET NULL"), nullable=True
    )
    offered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    offer_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
