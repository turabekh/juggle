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
    # A bespoke package created to fulfil ONE request-to-quote (Milestone C). It is a real
    # package so the whole deposit/balance/payout/invoice chain works unchanged, but it is
    # private to that quote — every public listing query excludes it, or a price quoted to one
    # family would show up on the marketplace.
    quote_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


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


# --- Request-to-quote (Milestone C, PRD §9 / ADR-0009) -----------------------


class QuoteRequestStatus(enum.StrEnum):
    submitted = "submitted"    # brief sent to the provider, no quote yet
    quoted = "quoted"          # a live quote exists (see PartyQuote for its state)
    accepted = "accepted"      # the parent accepted; a party booking exists
    declined = "declined"      # the provider passed on it
    withdrawn = "withdrawn"    # the parent pulled the brief
    expired = "expired"        # the quote lapsed and was never re-requested


class QuoteStatus(enum.StrEnum):
    sent = "sent"
    revision_requested = "revision_requested"  # the parent's ONE counter (ADR-0009)
    revised = "revised"                        # the provider's ONE revised offer
    accepted = "accepted"
    expired = "expired"
    withdrawn = "withdrawn"


class PartyQuoteRequest(UUIDPkMixin, TimestampMixin, Base):
    """A parent's structured brief for a bespoke party (PRD §9 request-to-quote).

    Structured fields only — there is no chat (EXT-1 §10). INV-3: the brief describes the
    party by **kid count and an age band**; it never carries a child's name or date of birth,
    and none of it is copied into analytics events.
    """

    __tablename__ = "party_quote_request"
    __table_args__ = (
        CheckConstraint("kid_count >= 1", name="ck_quote_req_kid_count"),
        CheckConstraint(
            "child_age_max >= child_age_min", name="ck_quote_req_age_band"
        ),
        CheckConstraint(
            "budget_cents IS NULL OR budget_cents >= 0", name="ck_quote_req_budget_nonneg"
        ),
        CheckConstraint("ends_at > starts_at", name="ck_quote_req_time_order"),
    )

    guardian_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    suburb: Mapped[str] = mapped_column(String(120), nullable=False)
    kid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    child_age_min: Mapped[int] = mapped_column(Integer, nullable=False)
    child_age_max: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # one field, not a thread
    status: Mapped[QuoteRequestStatus] = mapped_column(
        Enum(QuoteRequestStatus, name="party_quote_request_status"),
        default=QuoteRequestStatus.submitted,
        nullable=False,
    )


class PartyQuote(UUIDPkMixin, TimestampMixin, Base):
    """A provider's priced offer against a brief.

    The offer *is* a bespoke ``PartyPackage`` + one ``PartySlot`` (see
    ``docs/PLANS/milestone-C-request-to-quote.md``): accepting books that slot through the
    unchanged deposit rails, so no money code is duplicated here.

    Revisions happen in place and are capped at one (ADR-0009) — negotiation is bounded, not
    a chat. ``revision_count`` is the enforcement point and the DB CHECK is the backstop.
    """

    __tablename__ = "party_quote"
    __table_args__ = (
        CheckConstraint("total_cents >= 0", name="ck_party_quote_total_nonneg"),
        CheckConstraint("headcount >= 1", name="ck_party_quote_headcount"),
        CheckConstraint(
            "revision_count >= 0 AND revision_count <= 1", name="ck_party_quote_one_revision"
        ),
        # One live quote per brief; superseded/withdrawn ones don't block a fresh offer.
        Index(
            "uq_party_quote_active_per_request",
            "request_id",
            unique=True,
            postgresql_where=text("status NOT IN ('withdrawn', 'expired')"),
        ),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("party_quote_request.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The bespoke package/slot this offer is made of — booked as-is on accept.
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("party_package.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("party_slot.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    headcount: Mapped[int] = mapped_column(Integer, nullable=False)
    per_head_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # GST-inclusive
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)           # GST-inclusive
    message: Mapped[str | None] = mapped_column(Text, nullable=True)          # inclusions, 1 field
    revision_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # the parent's ask
    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("party_booking.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus, name="party_quote_status"),
        default=QuoteStatus.sent,
        nullable=False,
    )
