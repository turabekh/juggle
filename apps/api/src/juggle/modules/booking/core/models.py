"""Booking domain models: a per-session reservation and the children on it.

A cart can span multiple providers and sessions but settles in one payment
(PRD §7.4): each ``Booking`` is one session reservation, grouped by ``payment_id``
across the cart. ``BookingChild`` records which children attend plus any
provider-defined form answers captured at checkout.
"""

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class BookingStatus(enum.StrEnum):
    pending = "pending"        # awaiting payment
    confirmed = "confirmed"    # paid
    cancelled = "cancelled"
    refunded = "refunded"


class Booking(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "booking"
    __table_args__ = (
        # Idempotent booking creation (PRD §12): a client key maps to one booking.
        UniqueConstraint("idempotency_key", name="uq_booking_idempotency_key"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    guardian_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Set once the cart is paid; groups sibling bookings under one payment.
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # The seat hold this booking consumes — links the booking back to the seats
    # it occupies, so confirm/cancel act on the exact hold deterministically.
    seat_hold_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seat_hold.id", ondelete="SET NULL"), index=True, nullable=True
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"), default=BookingStatus.pending, nullable=False
    )
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)


class BookingChild(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "booking_child"
    __table_args__ = (
        UniqueConstraint("booking_id", "child_id", name="uq_booking_child"),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("booking.id", ondelete="CASCADE"), index=True, nullable=False
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("child.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Provider-defined required fields captured at checkout (PRD §7.4).
    form_answers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
