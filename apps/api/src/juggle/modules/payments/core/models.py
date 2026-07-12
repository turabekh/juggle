"""Payments domain models: a cart-level payment and per-provider payouts.

Stripe Connect Express with destination charges (PRD §8.4, §12): one ``Payment``
captures the guardian's cart; the platform application fee is 10% + GST on
marketplace bookings; each provider is paid via a ``Payout`` after the session
completes plus a dispute buffer. Fee % and payout delay are runtime config
(config module), not hard-coded here.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class PaymentStatus(enum.StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"
    partially_refunded = "partially_refunded"


class PayoutStatus(enum.StrEnum):
    scheduled = "scheduled"
    paid = "paid"
    held = "held"          # payout hold via admin (PRD §10.2)
    reversed = "reversed"


class Payment(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "payment"
    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="ck_payment_amount_nonneg"),
        CheckConstraint("application_fee_cents >= 0", name="ck_payment_fee_nonneg"),
        CheckConstraint("fee_gst_cents >= 0", name="ck_payment_fee_gst_nonneg"),
    )

    guardian_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    # Cart-level idempotency: a repeated checkout with the same key returns the
    # same payment/order instead of double-charging (PRD §7.4, §12).
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    application_fee_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # GST on the commission (ADR-0002); platform remits to the ATO. Deducted from payout.
    fee_gst_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Cumulative amount refunded so partial (per-session) refunds are exact and can't
    # exceed the charge; status becomes partially_refunded until it reaches amount_cents.
    refunded_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="aud", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.pending, nullable=False
    )


class StripeEvent(UUIDPkMixin, TimestampMixin, Base):
    """Webhook idempotency ledger (INV-2). Every processed Stripe event id is recorded
    with a UNIQUE constraint; a redelivery (Stripe is at-least-once) collides and is
    treated as an already-processed no-op."""

    __tablename__ = "stripe_event"

    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)


class Payout(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "payout"
    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="ck_payout_amount_nonneg"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Payout is per completed session (PRD §8.4).
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("session.id", ondelete="SET NULL"), index=True, nullable=True
    )
    stripe_transfer_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PayoutStatus] = mapped_column(
        Enum(PayoutStatus, name="payout_status"), default=PayoutStatus.scheduled, nullable=False
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
