"""Inventory domain models: transient seat holds placed during checkout.

A hold reserves ``quantity`` seats on a session for a TTL window (PRD §7.4,
§12). The inventory service increments ``session.seats_taken`` under a row lock
when a hold is created and decrements on expiry/release; the session CHECK
constraint guarantees the sum never exceeds capacity.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class SeatHoldStatus(enum.StrEnum):
    active = "active"        # counting against capacity; reclaimable when its TTL lapses
    reserved = "reserved"    # firm checkout reservation (ADR-0005) — counts, NOT TTL-reclaimed
    consumed = "consumed"    # converted into a confirmed booking
    released = "released"    # explicitly given back
    expired = "expired"      # TTL lapsed


class SeatHold(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "seat_hold"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_seat_hold_quantity_positive"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The guardian holding the seats (a user_account acting as guardian).
    held_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True, nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SeatHoldStatus] = mapped_column(
        Enum(SeatHoldStatus, name="seat_hold_status"),
        default=SeatHoldStatus.active,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
