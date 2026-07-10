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


def list_for_user(db: Session, user_id: uuid.UUID) -> list[NotificationLog]:
    return list(
        db.scalars(
            select(NotificationLog)
            .where(NotificationLog.user_account_id == user_id)
            .order_by(NotificationLog.created_at.desc())
        )
    )
