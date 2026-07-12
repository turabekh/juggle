"""Parties domain models (PRD §9, ADR-0006): the instant-book supply side.

A provider offers a ``PartyPackage`` at one of its venues (per-head pricing, a
headcount band, an optional weather clause for outdoor packages). Each bookable
time is a ``PartySlot`` — **capacity-1 inventory** (INV-1): one party per slot,
enforced by a partial UNIQUE on the booked link (added with the booking flow).

This module owns only the supply model + slot inventory here (Milestone B1). The
deposit-at-booking / T-7d balance / T-72h adjustment money flow lands in B2–B4,
all through the ``payments`` module (INV-2).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class PartyPackageStatus(enum.StrEnum):
    active = "active"
    archived = "archived"


class PartySlotStatus(enum.StrEnum):
    available = "available"
    held = "held"          # a booking is being placed (transient)
    booked = "booked"      # confirmed party
    cancelled = "cancelled"


class PartyPackage(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "party_package"
    __table_args__ = (
        CheckConstraint("per_head_price_cents >= 0", name="ck_party_pkg_price_nonneg"),
        CheckConstraint("min_headcount >= 1", name="ck_party_pkg_min_headcount"),
        CheckConstraint("max_headcount >= min_headcount", name="ck_party_pkg_headcount_band"),
        # deposit_pct is a whole-percent override; NULL means "use the config default".
        CheckConstraint(
            "deposit_pct IS NULL OR (deposit_pct >= 10 AND deposit_pct <= 100)",
            name="ck_party_pkg_deposit_pct",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    venue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("venue.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    per_head_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # GST-inclusive
    min_headcount: Mapped[int] = mapped_column(Integer, nullable=False)
    max_headcount: Mapped[int] = mapped_column(Integer, nullable=False)
    # Per-package deposit override (whole %); NULL → config `party_deposit_pct` (ADR-0007).
    deposit_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outdoor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # weather clause
    status: Mapped[PartyPackageStatus] = mapped_column(
        Enum(PartyPackageStatus, name="party_package_status"),
        default=PartyPackageStatus.active,
        nullable=False,
    )


class PartyBookingStatus(enum.StrEnum):
    pending_deposit = "pending_deposit"  # awaiting the deposit PaymentIntent to succeed
    confirmed = "confirmed"              # deposit paid; slot held (balance due at T-7d)
    cancelled = "cancelled"


class PartySlot(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "party_slot"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_party_slot_time_order"),
    )

    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("party_package.id", ondelete="CASCADE"), index=True, nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[PartySlotStatus] = mapped_column(
        Enum(PartySlotStatus, name="party_slot_status"),
        default=PartySlotStatus.available,
        nullable=False,
    )


class PartyBooking(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "party_booking"
    __table_args__ = (
        CheckConstraint("headcount >= 1", name="ck_party_booking_headcount"),
        CheckConstraint("total_cents >= 0", name="ck_party_booking_total_nonneg"),
        CheckConstraint(
            "deposit_cents >= 0 AND deposit_cents <= total_cents",
            name="ck_party_booking_deposit_range",
        ),
        # Capacity-1 (INV-1) DB backstop: at most one non-cancelled booking per slot.
        Index(
            "uq_party_slot_active_booking",
            "slot_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
    )

    slot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("party_slot.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("party_package.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    guardian_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    headcount: Mapped[int] = mapped_column(Integer, nullable=False)
    per_head_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # snapshot
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)          # GST-inclusive
    deposit_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    deposit_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment.id", ondelete="SET NULL"), nullable=True
    )
    balance_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment.id", ondelete="SET NULL"), nullable=True
    )
    # Balance auto-charge tracking (B3, ADR-0008).
    balance_captured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    balance_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_balance_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The provider payout this party fed (accrued when the balance captures), so a refund
    # claws back exactly that (ADR-0010 / F-PAY-5).
    payout_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payout.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[PartyBookingStatus] = mapped_column(
        Enum(PartyBookingStatus, name="party_booking_status"),
        default=PartyBookingStatus.pending_deposit,
        nullable=False,
    )
