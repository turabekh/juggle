"""Notifications service: render + send + log transactional email (PRD §7.4).

Low-level utility (like ``audit``): callers pass fully-formed domain data, this
module formats the message, sends it via the ``EmailGateway``, and records a
``NotificationLog``. It does not fetch domain data, so it never imports the
higher modules that call it.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.notifications.core.gateway import EmailGateway
from juggle.modules.notifications.core.ical import IcalEvent, build_ics
from juggle.modules.notifications.core.models import NotificationLog
from juggle.modules.notifications.core.schemas import ConfirmationSession

KIND_BOOKING_CONFIRMATION = "booking_confirmation"
KIND_SESSION_CANCELLATION = "session_cancellation"
KIND_WAITLIST_OFFER = "waitlist_offer"
KIND_PROVIDER_BROADCAST = "provider_broadcast"
KIND_SESSION_REMINDER = "session_reminder"
KIND_WHAT_TO_BRING = "what_to_bring"
KIND_SEAT_UNAVAILABLE_REFUND = "seat_unavailable_refund"
KIND_PARTY_PAYMENT_ACTION = "party_payment_action"
KIND_PARTY_CANCELLED = "party_cancelled"


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _record(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    to_email: str,
    kind: str,
    subject: str,
    detail: dict[str, object],
) -> NotificationLog:
    log = NotificationLog(
        user_account_id=user_id,
        to_email=to_email,
        kind=kind,
        subject=subject,
        detail=detail,
    )
    db.add(log)
    db.flush()
    return log


def order_ics(sessions: list[ConfirmationSession]) -> str:
    """Build the .ics for a set of booked sessions (used by the calendar route)."""
    return build_ics(
        [
            IcalEvent(
                uid=f"{s.session_id}@juggle",
                summary=s.title,
                starts_at=s.starts_at,
                ends_at=s.ends_at,
                location=s.venue_name,
                description=("For: " + ", ".join(s.children)) if s.children else None,
            )
            for s in sessions
        ]
    )


def notify_booking_confirmation(
    db: Session,
    *,
    user_id: uuid.UUID,
    to_email: str,
    sessions: list[ConfirmationSession],
    total_cents: int,
    gateway: EmailGateway,
) -> NotificationLog:
    subject = f"You're booked! {len(sessions)} session(s) confirmed"
    lines = ["Thanks for booking with Juggle. Here's your itinerary:", ""]
    for s in sessions:
        who = f" - {', '.join(s.children)}" if s.children else ""
        lines.append(f"* {s.title}{who}")
        lines.append(f"  {s.starts_at:%a %d %b, %I:%M%p} at {s.venue_name}")
    lines += ["", f"Total paid: {_money(total_cents)}", "", "A calendar invite is attached."]
    gateway.send(to=to_email, subject=subject, body="\n".join(lines), ics=order_ics(sessions))
    return _record(
        db,
        user_id=user_id,
        to_email=to_email,
        kind=KIND_BOOKING_CONFIRMATION,
        subject=subject,
        detail={"sessions": len(sessions), "total_cents": total_cents},
    )


def notify_session_cancellation(
    db: Session,
    *,
    user_id: uuid.UUID,
    to_email: str,
    session_title: str,
    starts_at: datetime,
    refunded: bool,
    gateway: EmailGateway,
) -> NotificationLog:
    subject = f"Cancelled: {session_title}"
    body = (
        f"We're sorry - {session_title} ({starts_at:%a %d %b}) has been cancelled by "
        "the provider.\n"
        + ("Your payment has been refunded in full." if refunded else "No payment was taken.")
    )
    gateway.send(to=to_email, subject=subject, body=body)
    return _record(
        db,
        user_id=user_id,
        to_email=to_email,
        kind=KIND_SESSION_CANCELLATION,
        subject=subject,
        detail={"refunded": refunded},
    )


def notify_seat_unavailable_refund(
    db: Session,
    *,
    user_id: uuid.UUID,
    to_email: str,
    total_cents: int,
    gateway: EmailGateway,
) -> NotificationLog:
    """The payment succeeded but the seat could not be secured — the charge has been
    refunded in full (ADR-0005 §3 auto-refund on a lost seat)."""
    subject = "Refunded: we couldn't secure your booking"
    body = (
        "Your payment went through, but the seat was no longer available by the time we "
        f"confirmed it. We've refunded {_money(total_cents)} in full — you have not been "
        "charged. Sorry for the inconvenience; please try booking again."
    )
    gateway.send(to=to_email, subject=subject, body=body)
    return _record(
        db,
        user_id=user_id,
        to_email=to_email,
        kind=KIND_SEAT_UNAVAILABLE_REFUND,
        subject=subject,
        detail={"refunded_cents": total_cents},
    )


def notify_party_payment_action_needed(
    db: Session,
    *,
    user_id: uuid.UUID,
    to_email: str,
    party_title: str,
    balance_cents: int,
    gateway: EmailGateway,
) -> NotificationLog:
    """A party balance charge failed — ask the host to update their card (ADR-0008 §2)."""
    subject = f"Action needed: payment for {party_title}"
    body = (
        f"We couldn't charge the remaining balance ({_money(balance_cents)}) for your booking of "
        f"{party_title}. Please update your card details so we can complete the payment — "
        "otherwise the booking will be cancelled and your deposit refunded."
    )
    gateway.send(to=to_email, subject=subject, body=body)
    return _record(
        db, user_id=user_id, to_email=to_email, kind=KIND_PARTY_PAYMENT_ACTION,
        subject=subject, detail={"balance_cents": balance_cents},
    )


def notify_party_cancelled(
    db: Session,
    *,
    user_id: uuid.UUID,
    to_email: str,
    party_title: str,
    gateway: EmailGateway,
) -> NotificationLog:
    """A party booking was cancelled; any refund due is processed (ADR-0008/0010)."""
    subject = f"Cancelled: {party_title}"
    body = (
        f"Your booking of {party_title} has been cancelled. Any refund due has been processed "
        "to your original payment method. You're welcome to book again."
    )
    gateway.send(to=to_email, subject=subject, body=body)
    return _record(
        db, user_id=user_id, to_email=to_email, kind=KIND_PARTY_CANCELLED,
        subject=subject, detail={},
    )


def notify_waitlist_offer(
    db: Session,
    *,
    user_id: uuid.UUID,
    to_email: str,
    session_title: str,
    starts_at: datetime,
    claim_deadline: datetime,
    gateway: EmailGateway,
) -> NotificationLog:
    subject = f"A seat opened up: {session_title}"
    body = (
        f"Good news — a seat has become available for {session_title} "
        f"({starts_at:%a %d %b, %I:%M%p}).\n\n"
        f"It's held for you until {claim_deadline:%a %d %b, %I:%M%p}. "
        "Claim it from your waitlist before then, or it passes to the next family."
    )
    gateway.send(to=to_email, subject=subject, body=body)
    return _record(
        db,
        user_id=user_id,
        to_email=to_email,
        kind=KIND_WAITLIST_OFFER,
        subject=subject,
        detail={"claim_deadline": claim_deadline.isoformat()},
    )


def notify_provider_broadcast(
    db: Session,
    *,
    user_id: uuid.UUID,
    to_email: str,
    organisation_name: str,
    subject: str,
    body: str,
    gateway: EmailGateway,
) -> NotificationLog:
    """Deliver a provider's broadcast to one booked family (PRD §8.5). The
    caller supplies fully-formed, provider-authored content."""
    full_subject = f"{organisation_name}: {subject}"
    gateway.send(to=to_email, subject=full_subject, body=body)
    return _record(
        db,
        user_id=user_id,
        to_email=to_email,
        kind=KIND_PROVIDER_BROADCAST,
        subject=full_subject,
        detail={"organisation_name": organisation_name},
    )


def notify_what_to_bring(
    db: Session,
    *,
    user_id: uuid.UUID,
    to_email: str,
    session_title: str,
    starts_at: datetime,
    what_to_bring: str,
    gateway: EmailGateway,
) -> NotificationLog:
    """The provider's what-to-bring note, sent automatically T-24h (PRD §8.5)."""
    subject = f"What to bring tomorrow: {session_title}"
    body = (
        f"{session_title} is coming up on {starts_at:%a %d %b at %I:%M%p}.\n\n"
        f"What to bring:\n{what_to_bring}"
    )
    gateway.send(to=to_email, subject=subject, body=body)
    return _record(
        db,
        user_id=user_id,
        to_email=to_email,
        kind=KIND_WHAT_TO_BRING,
        subject=subject,
        detail={},
    )


def notify_session_reminder(
    db: Session,
    *,
    user_id: uuid.UUID,
    to_email: str,
    session_title: str,
    starts_at: datetime,
    venue_name: str,
    window: str,
    gateway: EmailGateway,
) -> NotificationLog:
    """A pre-session reminder (PRD §7.5). ``window`` ('48h' / '3h') tunes the copy."""
    when = "in 2 days" if window == "48h" else "soon"
    subject = f"Reminder: {session_title} is {when}"
    body = (
        f"Just a heads-up — {session_title} starts {starts_at:%a %d %b at %I:%M%p} "
        f"at {venue_name}.\n\n"
        "Please pack a hat, sunscreen, a labelled water bottle and morning tea. "
        "See you there!"
    )
    gateway.send(to=to_email, subject=subject, body=body)
    return _record(
        db,
        user_id=user_id,
        to_email=to_email,
        kind=KIND_SESSION_REMINDER,
        subject=subject,
        detail={"window": window},
    )


def list_for_user(db: Session, user_id: uuid.UUID) -> list[NotificationLog]:
    return list(
        db.scalars(
            select(NotificationLog)
            .where(NotificationLog.user_account_id == user_id)
            .order_by(NotificationLog.created_at.desc())
        )
    )
