"""Reviews service (PRD §7.6).

Sits above ``booking`` in the layering: it verifies a review against the exact
completed booking that entitles it (verified-booking-only), screens the body for
child names (child PII must never appear in review content), holds new reviews in
a moderation queue, and lets providers reply once. Aggregates (avg + count) are
computed over *published* reviews only, so nothing unmoderated is ever surfaced.

Like ``roster``, this module reads a few lower modules' models directly for the
verification join (``Booking``/``BookingChild``/``Child``) and calls their
services for enrichment (catalog/org). Every consequential action is audited.
"""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from juggle.modules.audit.core import service as audit_service
from juggle.modules.booking.core.models import Booking, BookingChild, BookingStatus
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.identity.core.models import Child, UserAccount
from juggle.modules.org.core import service as org_service
from juggle.modules.reviews.core.models import Review, ReviewStatus
from juggle.modules.reviews.core.schemas import (
    RatingSummary,
    ReviewableBooking,
    ReviewListOut,
    ReviewOut,
    ReviewPublicOut,
)


class BookingNotFound(Exception):
    """No such booking, or it does not belong to the author."""


class BookingNotReviewable(Exception):
    """Booking is not confirmed, or its session has not finished yet."""


class AlreadyReviewed(Exception):
    """A review already exists for this booking (one per booking)."""


class ChildNameInReview(Exception):
    """Body mentions a child's first name — blocked at submission (PRD §7.6)."""


class ReviewNotFound(Exception):
    """No such review."""


class NotProviderMember(Exception):
    """Caller is not a member of the reviewed organisation."""


class ReviewNotPublished(Exception):
    """Action requires a published review (e.g. provider reply)."""


def _now() -> datetime:
    return datetime.now(UTC)


def _author_label(user: UserAccount | None) -> str:
    """A privacy-preserving byline: first name only, else a neutral label. Never
    the child's name and never the guardian's surname/email."""
    if user is not None and user.full_name:
        first = user.full_name.strip().split(" ", 1)[0]
        if first:
            return first
    return "Verified parent"


def _child_first_names(db: Session, booking_id: uuid.UUID) -> list[str]:
    stmt = (
        select(Child.first_name)
        .join(BookingChild, BookingChild.child_id == Child.id)
        .where(BookingChild.booking_id == booking_id)
    )
    return [name for name in db.scalars(stmt)]


def _mentions_child(body: str, child_names: list[str]) -> bool:
    """Whole-word, case-insensitive match of any child first name in the body."""
    lowered = body.lower()
    return any(
        re.search(rf"\b{re.escape(name.lower())}\b", lowered)
        for name in child_names
        if name.strip()
    )


def _review_out(db: Session, review: Review) -> ReviewOut:
    author = db.get(UserAccount, review.author_id)
    program = catalog_service.get_program(db, review.program_id)
    return ReviewOut(
        id=review.id,
        booking_id=review.booking_id,
        organisation_id=review.organisation_id,
        program_id=review.program_id,
        session_id=review.session_id,
        rating=review.rating,
        body=review.body,
        status=review.status.value,
        rejection_reason=review.rejection_reason,
        author_label=_author_label(author),
        program_title=program.title if program is not None else "",
        provider_reply=review.provider_reply,
        provider_reply_at=review.provider_reply_at,
        created_at=review.created_at,
    )


def _public_out(db: Session, review: Review) -> ReviewPublicOut:
    author = db.get(UserAccount, review.author_id)
    return ReviewPublicOut(
        id=review.id,
        rating=review.rating,
        body=review.body,
        author_label=_author_label(author),
        created_at=review.created_at,
        provider_reply=review.provider_reply,
        provider_reply_at=review.provider_reply_at,
    )


# --- guardian: submit + browse own ------------------------------------------


def submit_review(
    db: Session,
    *,
    booking_id: uuid.UUID,
    author_id: uuid.UUID,
    rating: int,
    body: str,
) -> ReviewOut:
    """Create a pending review for a completed booking the author owns."""
    booking = db.get(Booking, booking_id)
    if booking is None or booking.guardian_id != author_id:
        raise BookingNotFound(str(booking_id))
    if booking.status is not BookingStatus.confirmed:
        raise BookingNotReviewable(str(booking_id))

    session = catalog_service.get_session(db, booking.session_id)
    if session is None:
        raise BookingNotReviewable(str(booking_id))
    if session.ends_at > _now():
        # Can't review a session that hasn't happened yet.
        raise BookingNotReviewable(str(booking_id))

    if db.scalar(select(Review.id).where(Review.booking_id == booking_id)) is not None:
        raise AlreadyReviewed(str(booking_id))

    if _mentions_child(body, _child_first_names(db, booking_id)):
        raise ChildNameInReview(str(booking_id))

    review = Review(
        booking_id=booking_id,
        author_id=author_id,
        organisation_id=booking.organisation_id,
        program_id=session.program_id,
        session_id=session.id,
        rating=rating,
        body=body.strip(),
        status=ReviewStatus.pending,
    )
    db.add(review)
    db.flush()
    audit_service.record(
        db,
        action="review.submitted",
        actor_id=author_id,
        entity_type="review",
        entity_id=str(review.id),
        detail={"rating": rating, "organisation_id": str(booking.organisation_id)},
    )
    return _review_out(db, review)


def list_for_author(db: Session, author_id: uuid.UUID) -> list[ReviewOut]:
    reviews = db.scalars(
        select(Review)
        .where(Review.author_id == author_id)
        .order_by(Review.created_at.desc())
    )
    return [_review_out(db, r) for r in reviews]


def reviewable_bookings(db: Session, author_id: uuid.UUID) -> list[ReviewableBooking]:
    """Confirmed bookings whose session has finished and that have no review yet."""
    now = _now()
    reviewed = select(Review.booking_id).where(Review.author_id == author_id)
    stmt = (
        select(Booking)
        .where(
            Booking.guardian_id == author_id,
            Booking.status == BookingStatus.confirmed,
            Booking.id.not_in(reviewed),
        )
        .order_by(Booking.created_at.desc())
    )
    out: list[ReviewableBooking] = []
    for booking in db.scalars(stmt):
        session = catalog_service.get_session(db, booking.session_id)
        if session is None or session.ends_at > now:
            continue
        program = catalog_service.get_program(db, session.program_id)
        org = org_service.get_organisation(db, booking.organisation_id)
        out.append(
            ReviewableBooking(
                booking_id=booking.id,
                session_id=session.id,
                program_title=program.title if program is not None else "",
                organisation_name=org.name if org is not None else "",
                starts_at=session.starts_at,
            )
        )
    return out


# --- public: read published --------------------------------------------------


def _summary_for(db: Session, *, column: object, value: uuid.UUID) -> RatingSummary:
    avg, count = db.execute(
        select(func.avg(Review.rating), func.count(Review.id)).where(
            column == value,  # type: ignore[arg-type]
            Review.status == ReviewStatus.published,
        )
    ).one()
    return RatingSummary(
        average=round(float(avg), 2) if avg is not None else None,
        count=int(count),
    )


def _published(db: Session, *, column: object, value: uuid.UUID) -> list[Review]:
    return list(
        db.scalars(
            select(Review)
            .where(
                column == value,  # type: ignore[arg-type]
                Review.status == ReviewStatus.published,
            )
            .order_by(Review.created_at.desc())
        )
    )


def list_for_organisation(db: Session, organisation_id: uuid.UUID) -> ReviewListOut:
    summary = _summary_for(db, column=Review.organisation_id, value=organisation_id)
    items = _published(db, column=Review.organisation_id, value=organisation_id)
    return ReviewListOut(summary=summary, items=[_public_out(db, r) for r in items])


def list_for_program(db: Session, program_id: uuid.UUID) -> ReviewListOut:
    summary = _summary_for(db, column=Review.program_id, value=program_id)
    items = _published(db, column=Review.program_id, value=program_id)
    return ReviewListOut(summary=summary, items=[_public_out(db, r) for r in items])


def organisation_summary(db: Session, organisation_id: uuid.UUID) -> RatingSummary:
    return _summary_for(db, column=Review.organisation_id, value=organisation_id)


# --- provider: right-of-reply + own reviews ---------------------------------


def list_for_provider(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> list[ReviewOut]:
    """All published reviews for an org the caller belongs to (for reply/manage)."""
    if org_service.get_member(db, organisation_id, actor_id) is None:
        raise NotProviderMember(str(organisation_id))
    reviews = db.scalars(
        select(Review)
        .where(
            Review.organisation_id == organisation_id,
            Review.status == ReviewStatus.published,
        )
        .order_by(Review.created_at.desc())
    )
    return [_review_out(db, r) for r in reviews]


def provider_reply(
    db: Session, *, review_id: uuid.UUID, actor_id: uuid.UUID, reply: str
) -> ReviewOut:
    review = db.get(Review, review_id)
    if review is None:
        raise ReviewNotFound(str(review_id))
    if org_service.get_member(db, review.organisation_id, actor_id) is None:
        raise NotProviderMember(str(review.organisation_id))
    if review.status is not ReviewStatus.published:
        raise ReviewNotPublished(str(review_id))
    review.provider_reply = reply.strip()
    review.provider_reply_at = _now()
    db.flush()
    audit_service.record(
        db,
        action="review.replied",
        actor_id=actor_id,
        entity_type="review",
        entity_id=str(review.id),
        detail={"organisation_id": str(review.organisation_id)},
    )
    return _review_out(db, review)


# --- admin: moderation queue -------------------------------------------------


def list_for_moderation(
    db: Session, *, status: ReviewStatus = ReviewStatus.pending
) -> list[ReviewOut]:
    reviews = db.scalars(
        select(Review).where(Review.status == status).order_by(Review.created_at.asc())
    )
    return [_review_out(db, r) for r in reviews]


def moderate(
    db: Session,
    *,
    review_id: uuid.UUID,
    moderator_id: uuid.UUID,
    approve: bool,
    reason: str | None = None,
) -> ReviewOut:
    review = db.get(Review, review_id)
    if review is None:
        raise ReviewNotFound(str(review_id))
    review.status = ReviewStatus.published if approve else ReviewStatus.rejected
    review.rejection_reason = None if approve else reason
    review.moderated_at = _now()
    review.moderator_id = moderator_id
    db.flush()
    audit_service.record(
        db,
        action="review.moderated",
        actor_id=moderator_id,
        entity_type="review",
        entity_id=str(review.id),
        detail={"approve": approve, "reason": reason},
    )
    return _review_out(db, review)
