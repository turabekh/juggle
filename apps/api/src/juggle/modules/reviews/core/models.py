"""Review domain models (PRD §7.6): verified-booking-only provider reviews.

A ``Review`` is written by a guardian against the provider (organisation) they
booked, and is anchored to the exact completed ``booking`` that entitles them to
write it — verification is a data invariant, not a UI convenience. Reviews start
``pending`` and only surface publicly once a moderator publishes them; providers
may add a single right-of-reply. The 1–5 rating bound and one-review-per-booking
rule are enforced at the DB layer (CHECK + UNIQUE), never only in Python.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from juggle.common import TimestampMixin, UUIDPkMixin
from juggle.db import Base


class ReviewStatus(enum.StrEnum):
    pending = "pending"        # awaiting moderation (not shown publicly)
    published = "published"    # visible on provider/listing pages
    rejected = "rejected"      # moderator declined (kept for audit, hidden)


class Review(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "review"
    __table_args__ = (
        # One review per booking: the booking is the verification token (PRD §7.6).
        UniqueConstraint("booking_id", name="uq_review_booking"),
        # 1–5 stars enforced at the DB layer, not just by the API schema.
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
    )

    # The completed, confirmed booking that entitles this review to exist.
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("booking.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Denormalised anchors so provider/listing aggregates read without a booking join.
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), index=True, nullable=False
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("program.id", ondelete="CASCADE"), index=True, nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), index=True, nullable=False
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status"),
        default=ReviewStatus.pending,
        nullable=False,
        index=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    moderator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )

    # Provider right-of-reply (PRD §7.6): a single response to a published review.
    provider_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_reply_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
