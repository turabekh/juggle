"""Scheduler service: one idempotent maintenance tick (PRD §7.5, §7.7).

The top of the layering — it orchestrates lower modules on a periodic beat that a
worker or cron drives. Every job is safe to run repeatedly:

  * ``reclaim_all_expired`` — free seats from lapsed holds proactively.
  * ``waitlist.process_all`` — offer freed seats / expire lapsed offers.
  * ``_send_reminders`` — T-48h / T-3h pre-session emails, deduped by a
    ``SessionReminder`` marker so each window fires exactly once per session.

``now`` is injected so behaviour is deterministic and testable.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.booking.core import service as booking_service
from juggle.modules.booking.core.models import Booking, BookingStatus
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.catalog.core.models import Session as ProgramSession
from juggle.modules.catalog.core.models import SessionStatus, Venue
from juggle.modules.identity.core import service as identity_service
from juggle.modules.inventory.core import service as inventory_service
from juggle.modules.notifications.core import service as notifications_service
from juggle.modules.notifications.core.gateway import EmailGateway, get_email_gateway
from juggle.modules.org.core import service as org_service
from juggle.modules.parties.core import service as parties_service
from juggle.modules.payments.core.gateway import PaymentGateway, get_payment_gateway
from juggle.modules.scheduler.core.models import SessionReminder
from juggle.modules.scheduler.core.schemas import JobSummary
from juggle.modules.waitlist.core import service as waitlist_service

# (marker key, hours before start). Ordered widest-first so a session created
# late still gets its nearest-window reminder.
REMINDER_WINDOWS: list[tuple[str, int]] = [("48h", 48), ("3h", 3)]

# Marker + lead time for the automated "what to bring" note (PRD §8.5).
WHAT_TO_BRING_WINDOW = "wtb"
WHAT_TO_BRING_HOURS = 24


def _confirmed_guardian_ids(db: Session, session_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(Booking.guardian_id)
            .where(
                Booking.session_id == session_id,
                Booking.status == BookingStatus.confirmed,
            )
            .distinct()
        )
    )


def _already_reminded(db: Session, session_id: uuid.UUID, window: str) -> bool:
    return (
        db.scalar(
            select(SessionReminder.id).where(
                SessionReminder.session_id == session_id,
                SessionReminder.window == window,
            )
        )
        is not None
    )


def _send_reminders(db: Session, *, now: datetime, gateway: EmailGateway) -> int:
    sent = 0
    for window, hours in REMINDER_WINDOWS:
        horizon = now + timedelta(hours=hours)
        sessions = db.scalars(
            select(ProgramSession).where(
                ProgramSession.status != SessionStatus.cancelled,
                ProgramSession.starts_at > now,
                ProgramSession.starts_at <= horizon,
            )
        ).all()
        for session in sessions:
            if _already_reminded(db, session.id, window):
                continue
            program = catalog_service.get_program(db, session.program_id)
            venue = db.get(Venue, session.venue_id)
            title = program.title if program is not None else "your session"
            venue_name = venue.name if venue is not None else "the venue"

            count = 0
            for guardian_id in _confirmed_guardian_ids(db, session.id):
                guardian = identity_service.get_user(db, guardian_id)
                if guardian is None:
                    continue
                notifications_service.notify_session_reminder(
                    db,
                    user_id=guardian.id,
                    to_email=guardian.email,
                    session_title=title,
                    starts_at=session.starts_at,
                    venue_name=venue_name,
                    window=window,
                    gateway=gateway,
                )
                count += 1

            # Record the marker even when nobody is booked, so we don't re-scan
            # this window every tick; late bookers are still caught by T-3h.
            db.add(
                SessionReminder(
                    session_id=session.id, window=window, recipient_count=count
                )
            )
            db.flush()
            sent += count
    return sent


def _send_what_to_bring(db: Session, *, now: datetime, gateway: EmailGateway) -> int:
    """T-24h: email the provider's what-to-bring note to confirmed families, once."""
    horizon = now + timedelta(hours=WHAT_TO_BRING_HOURS)
    sessions = db.scalars(
        select(ProgramSession).where(
            ProgramSession.status != SessionStatus.cancelled,
            ProgramSession.starts_at > now,
            ProgramSession.starts_at <= horizon,
            ProgramSession.what_to_bring.is_not(None),
        )
    ).all()

    sent = 0
    for session in sessions:
        if not (session.what_to_bring or "").strip():
            continue
        if _already_reminded(db, session.id, WHAT_TO_BRING_WINDOW):
            continue
        program = catalog_service.get_program(db, session.program_id)
        title = program.title if program is not None else "your session"

        count = 0
        for guardian_id in _confirmed_guardian_ids(db, session.id):
            guardian = identity_service.get_user(db, guardian_id)
            if guardian is None:
                continue
            notifications_service.notify_what_to_bring(
                db,
                user_id=guardian.id,
                to_email=guardian.email,
                session_title=title,
                starts_at=session.starts_at,
                what_to_bring=session.what_to_bring or "",
                gateway=gateway,
            )
            count += 1
        db.add(
            SessionReminder(
                session_id=session.id, window=WHAT_TO_BRING_WINDOW, recipient_count=count
            )
        )
        db.flush()
        sent += count
    return sent


def run_due_jobs(
    db: Session,
    *,
    now: datetime,
    gateway: EmailGateway | None = None,
    payment_gateway: PaymentGateway | None = None,
) -> JobSummary:
    """Execute one maintenance tick. Idempotent; safe to call on any cadence."""
    if gateway is None:
        gateway = get_email_gateway()
    if payment_gateway is None:
        payment_gateway = get_payment_gateway()

    # Free abandoned checkouts BEFORE waitlist processing so the freed seats can be
    # offered on this same tick.
    abandoned = booking_service.sweep_abandoned_checkouts(
        db, gateway=payment_gateway, now=now
    )
    party_deposits_swept = parties_service.sweep_abandoned_deposits(
        db, gateway=payment_gateway, now=now
    )
    party_balances_processed = parties_service.process_party_balances(
        db, gateway=payment_gateway, email_gateway=gateway, now=now
    )
    holds_reclaimed = inventory_service.reclaim_all_expired(db, now=now)
    waitlist_run = waitlist_service.process_all(db)
    reminders_sent = _send_reminders(db, now=now, gateway=gateway)
    what_to_bring_sent = _send_what_to_bring(db, now=now, gateway=gateway)
    compliance_expired = org_service.expire_due_compliance(db, today=now.date())

    return JobSummary(
        holds_reclaimed=holds_reclaimed,
        abandoned_checkouts_swept=abandoned,
        party_deposits_swept=party_deposits_swept,
        party_balances_processed=party_balances_processed,
        waitlist_sessions_processed=waitlist_run.sessions_processed,
        waitlist_offers_made=waitlist_run.offers_made,
        waitlist_offers_expired=waitlist_run.offers_expired,
        reminders_sent=reminders_sent,
        what_to_bring_sent=what_to_bring_sent,
        compliance_expired=compliance_expired,
    )
