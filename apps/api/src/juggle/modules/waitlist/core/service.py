"""Waitlist service (PRD §7.7).

Sits above ``booking`` in the layering and drives everything by **reconciliation**
against live inventory — it never reaches down into the checkout path, so the
core booking/inventory flow is untouched:

  * ``join_waitlist`` — only when the session is genuinely sold out.
  * ``reconcile_session`` — the engine. Under the session row lock it (1) resolves
    outstanding offers (claimed / lapsed), then (2) offers each free seat to the
    front of the FIFO queue by reserving it with a claim-window seat hold and
    emailing the family. A claim is just a normal checkout against that hold.
  * Expiry has no scheduler yet, so reconciliation runs lazily whenever the queue
    is read and via an admin ops sweep (``process_all``) — the same pattern as
    payout release.

Offer holds are placed through ``inventory.hold_seats`` so the proven oversell
guard (row lock + CHECK constraint) still owns every seat mutation.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from juggle.modules.audit.core import service as audit_service
from juggle.modules.booking.core.models import Booking, BookingStatus
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.catalog.core.models import SessionStatus
from juggle.modules.config.core import service as config_service
from juggle.modules.identity.core import service as identity_service
from juggle.modules.inventory.core import service as inventory_service
from juggle.modules.inventory.core.models import SeatHold, SeatHoldStatus
from juggle.modules.notifications.core import service as notifications_service
from juggle.modules.notifications.core.gateway import get_email_gateway
from juggle.modules.org.core import service as org_service
from juggle.modules.waitlist.core.models import (
    ACTIVE_STATUSES,
    WaitlistEntry,
    WaitlistStatus,
)
from juggle.modules.waitlist.core.schemas import (
    SessionWaitlistOut,
    WaitlistEntryOut,
    WaitlistRunResult,
)


class SessionNotFound(Exception):
    """No such session (or it is not joinable)."""


class SessionNotSoldOut(Exception):
    """The session still has seats — book directly instead of waitlisting."""


class AlreadyOnWaitlist(Exception):
    """The guardian already has an active place in this session's queue."""


class EntryNotFound(Exception):
    """No such waitlist entry belonging to the caller."""


class NotOrgMember(Exception):
    """Caller is not a member of the organisation running this session."""


def _now() -> datetime:
    return datetime.now(UTC)


def _active_entry(
    db: Session, *, session_id: uuid.UUID, guardian_id: uuid.UUID
) -> WaitlistEntry | None:
    return db.scalar(
        select(WaitlistEntry).where(
            WaitlistEntry.session_id == session_id,
            WaitlistEntry.guardian_id == guardian_id,
            WaitlistEntry.status.in_(ACTIVE_STATUSES),
        )
    )


def _has_booking_on_hold(db: Session, hold_id: uuid.UUID) -> bool:
    """True once the offered guardian has checked out against the offer hold."""
    return (
        db.scalar(
            select(Booking.id).where(
                Booking.seat_hold_id == hold_id,
                Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed]),
            )
        )
        is not None
    )


def _position(db: Session, entry: WaitlistEntry) -> int | None:
    """1-based place among still-waiting entries; None once offered/resolved."""
    if entry.status is not WaitlistStatus.waiting:
        return None
    ahead = db.scalar(
        select(func.count(WaitlistEntry.id)).where(
            WaitlistEntry.session_id == entry.session_id,
            WaitlistEntry.status == WaitlistStatus.waiting,
            WaitlistEntry.seq < entry.seq,
        )
    )
    return int(ahead or 0) + 1


def _entry_out(db: Session, entry: WaitlistEntry) -> WaitlistEntryOut:
    session = catalog_service.get_session(db, entry.session_id)
    program = (
        catalog_service.get_program(db, session.program_id) if session is not None else None
    )
    org = (
        org_service.get_organisation(db, program.organisation_id)
        if program is not None
        else None
    )
    return WaitlistEntryOut(
        id=entry.id,
        session_id=entry.session_id,
        status=entry.status.value,
        position=_position(db, entry),
        program_title=program.title if program is not None else "",
        organisation_name=org.name if org is not None else "",
        starts_at=session.starts_at if session is not None else _now(),
        ends_at=session.ends_at if session is not None else _now(),
        offer_hold_id=entry.offer_hold_id,
        offer_expires_at=entry.offer_expires_at,
        created_at=entry.created_at,
    )


# --- guardian: join / leave / view ------------------------------------------


def join_waitlist(
    db: Session, *, session_id: uuid.UUID, guardian_id: uuid.UUID
) -> WaitlistEntryOut:
    session = inventory_service.availability(db, session_id)  # reclaims → honest count
    if session is None or session.status is SessionStatus.cancelled:
        raise SessionNotFound(str(session_id))
    if session.seats_remaining > 0:
        raise SessionNotSoldOut(str(session_id))
    if _active_entry(db, session_id=session_id, guardian_id=guardian_id) is not None:
        raise AlreadyOnWaitlist(str(session_id))

    entry = WaitlistEntry(
        session_id=session_id, guardian_id=guardian_id, status=WaitlistStatus.waiting
    )
    db.add(entry)
    db.flush()
    audit_service.record(
        db,
        action="waitlist.joined",
        actor_id=guardian_id,
        entity_type="waitlist_entry",
        entity_id=str(entry.id),
        detail={"session_id": str(session_id)},
    )
    return _entry_out(db, entry)


def leave_waitlist(db: Session, *, entry_id: uuid.UUID, guardian_id: uuid.UUID) -> None:
    entry = db.get(WaitlistEntry, entry_id)
    if entry is None or entry.guardian_id != guardian_id:
        raise EntryNotFound(str(entry_id))
    if entry.status not in ACTIVE_STATUSES:
        return  # already resolved
    # Give back a reserved seat, if they were mid-offer.
    if entry.status is WaitlistStatus.offered and entry.offer_hold_id is not None:
        inventory_service.force_release(db, hold_id=entry.offer_hold_id)
    entry.status = WaitlistStatus.cancelled
    db.flush()
    audit_service.record(
        db,
        action="waitlist.left",
        actor_id=guardian_id,
        entity_type="waitlist_entry",
        entity_id=str(entry.id),
    )
    # Freed the offered seat — let the next family have it.
    reconcile_session(db, entry.session_id)


def list_for_guardian(db: Session, guardian_id: uuid.UUID) -> list[WaitlistEntryOut]:
    # Reconcile the sessions this guardian is queued on so offers/expiries surface.
    session_ids = db.scalars(
        select(WaitlistEntry.session_id)
        .where(
            WaitlistEntry.guardian_id == guardian_id,
            WaitlistEntry.status.in_(ACTIVE_STATUSES),
        )
        .distinct()
    ).all()
    for session_id in session_ids:
        reconcile_session(db, session_id)

    entries = db.scalars(
        select(WaitlistEntry)
        .where(
            WaitlistEntry.guardian_id == guardian_id,
            WaitlistEntry.status.in_(ACTIVE_STATUSES),
        )
        .order_by(WaitlistEntry.created_at)
    ).all()
    return [_entry_out(db, e) for e in entries]


def session_waitlist(
    db: Session, *, session_id: uuid.UUID, actor_id: uuid.UUID
) -> SessionWaitlistOut:
    session = catalog_service.get_session(db, session_id)
    if session is None:
        raise SessionNotFound(str(session_id))
    program = catalog_service.get_program(db, session.program_id)
    if program is None:
        raise SessionNotFound(str(session_id))
    if org_service.get_member(db, program.organisation_id, actor_id) is None:
        raise NotOrgMember(str(program.organisation_id))

    reconcile_session(db, session_id)
    rows = db.execute(
        select(WaitlistEntry.status, func.count(WaitlistEntry.id))
        .where(WaitlistEntry.session_id == session_id)
        .group_by(WaitlistEntry.status)
    ).all()
    counts: dict[WaitlistStatus, int] = {status: int(n) for status, n in rows}
    return SessionWaitlistOut(
        session_id=session_id,
        waiting=counts.get(WaitlistStatus.waiting, 0),
        offered=counts.get(WaitlistStatus.offered, 0),
    )


# --- the reconciliation engine ----------------------------------------------


def reconcile_session(db: Session, session_id: uuid.UUID) -> tuple[int, int]:
    """Resolve outstanding offers then fill free seats. Returns (made, expired)."""
    session = inventory_service.availability(db, session_id)  # locks + reclaims holds
    if session is None:
        return (0, 0)

    if session.status is SessionStatus.cancelled:
        expired = 0
        for entry in db.scalars(
            select(WaitlistEntry).where(
                WaitlistEntry.session_id == session_id,
                WaitlistEntry.status.in_(ACTIVE_STATUSES),
            )
        ):
            entry.status = WaitlistStatus.expired
            expired += 1
        db.flush()
        return (0, expired)

    offers_expired = 0
    # 1. Resolve current offers: claimed (they booked) or lapsed (hold gone).
    for entry in db.scalars(
        select(WaitlistEntry).where(
            WaitlistEntry.session_id == session_id,
            WaitlistEntry.status == WaitlistStatus.offered,
        )
    ):
        hold = (
            db.get(SeatHold, entry.offer_hold_id)
            if entry.offer_hold_id is not None
            else None
        )
        if entry.offer_hold_id is not None and _has_booking_on_hold(db, entry.offer_hold_id):
            entry.status = WaitlistStatus.claimed
        elif hold is None or hold.status is not SeatHoldStatus.active:
            entry.status = WaitlistStatus.expired
            offers_expired += 1
        # else: still validly offered — leave it
    db.flush()

    # 2. Offer each free seat to the front of the queue.
    offers_made = 0
    window_minutes = config_service.waitlist_claim_window_minutes(db)
    program = catalog_service.get_program(db, session.program_id)
    title = program.title if program is not None else "your session"

    waiting = db.scalars(
        select(WaitlistEntry)
        .where(
            WaitlistEntry.session_id == session_id,
            WaitlistEntry.status == WaitlistStatus.waiting,
        )
        .order_by(WaitlistEntry.seq)
    ).all()

    for entry in waiting:
        try:
            hold, _ = inventory_service.hold_seats(
                db,
                session_id=session_id,
                held_by_id=entry.guardian_id,
                quantity=1,
                ttl_seconds=window_minutes * 60,
            )
        except inventory_service.SoldOut:
            break  # no free seats left to offer

        now = _now()
        deadline = now + timedelta(minutes=window_minutes)
        entry.status = WaitlistStatus.offered
        entry.offer_hold_id = hold.id
        entry.offered_at = now
        entry.offer_expires_at = deadline
        db.flush()

        guardian = identity_service.get_user(db, entry.guardian_id)
        if guardian is not None:
            notifications_service.notify_waitlist_offer(
                db,
                user_id=guardian.id,
                to_email=guardian.email,
                session_title=title,
                starts_at=session.starts_at,
                claim_deadline=deadline,
                gateway=get_email_gateway(),
            )
        audit_service.record(
            db,
            action="waitlist.offered",
            actor_id=None,
            entity_type="waitlist_entry",
            entity_id=str(entry.id),
            detail={"session_id": str(session_id), "guardian_id": str(entry.guardian_id)},
        )
        offers_made += 1

    return (offers_made, offers_expired)


def process_all(db: Session) -> WaitlistRunResult:
    """Ops sweep (cron-friendly): reconcile every session with an active queue."""
    session_ids = db.scalars(
        select(WaitlistEntry.session_id)
        .where(WaitlistEntry.status.in_(ACTIVE_STATUSES))
        .distinct()
    ).all()
    made = expired = 0
    for session_id in session_ids:
        m, e = reconcile_session(db, session_id)
        made += m
        expired += e
    return WaitlistRunResult(
        sessions_processed=len(session_ids), offers_made=made, offers_expired=expired
    )
