"""Inventory service: seat holds with a TTL and a transactional oversell guard.

Inventory correctness is the product (PRD §12). The rule enforced here:

  * ``catalog.Session.seats_taken`` is the single source of truth for occupancy,
    and inventory is its only writer.
  * Every mutation takes a ``SELECT ... FOR UPDATE`` row lock on the session, so
    two concurrent checkouts for the last seat are serialised — one wins, the
    other sees zero remaining.
  * The ``ck_session_no_oversell`` CHECK constraint is the ultimate backstop: if
    the application logic were ever wrong, the database still refuses the write.

Inventory sits above catalog in the layering, so it may operate on the Session
model directly to hold the lock.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from juggle.modules.catalog.core.models import Session as ProgramSession
from juggle.modules.catalog.core.models import SessionStatus
from juggle.modules.config.core import service as config_service
from juggle.modules.events.core import service as events_service
from juggle.modules.inventory.core.models import SeatHold, SeatHoldStatus


class SessionNotFound(Exception):
    """No such session (or it is not holdable)."""


class SoldOut(Exception):
    """Not enough seats remain to satisfy the requested quantity."""

    def __init__(self, remaining: int) -> None:
        self.remaining = remaining
        super().__init__(f"only {remaining} seat(s) remaining")


class HoldNotFound(Exception):
    """No active hold with that id belonging to the caller."""


class TooManyHolds(Exception):
    """The guardian already holds the maximum concurrent seats (anti-hoarding)."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"at most {limit} active holds allowed")


def _lock_session(db: Session, session_id: uuid.UUID) -> ProgramSession | None:
    return db.execute(
        select(ProgramSession).where(ProgramSession.id == session_id).with_for_update()
    ).scalar_one_or_none()


def _reclaim_expired(db: Session, session_obj: ProgramSession, *, now: datetime) -> int:
    """Release seats from active holds whose TTL has lapsed. Runs under the lock.
    Returns the number of holds reclaimed."""
    expired = db.scalars(
        select(SeatHold).where(
            SeatHold.session_id == session_obj.id,
            SeatHold.status == SeatHoldStatus.active,
            SeatHold.expires_at < now,
        )
    ).all()
    for hold in expired:
        hold.status = SeatHoldStatus.expired
        session_obj.seats_taken -= hold.quantity
    if expired:
        db.flush()
    return len(expired)


def reclaim_all_expired(db: Session, *, now: datetime | None = None) -> int:
    """Proactively reclaim every session's lapsed holds (for the scheduler sweep).

    Lazy reclaim only runs when a session is read/mutated; this walks all sessions
    that currently hold an expired active hold and frees the seats under each
    session's row lock. Returns the total number of holds reclaimed.
    """
    if now is None:
        now = datetime.now(UTC)
    session_ids = db.scalars(
        select(SeatHold.session_id)
        .where(SeatHold.status == SeatHoldStatus.active, SeatHold.expires_at < now)
        .distinct()
    ).all()
    total = 0
    for session_id in session_ids:
        session_obj = _lock_session(db, session_id)
        if session_obj is not None:
            total += _reclaim_expired(db, session_obj, now=now)
    return total


def hold_seats(
    db: Session,
    *,
    session_id: uuid.UUID,
    held_by_id: uuid.UUID,
    quantity: int,
    ttl_seconds: int | None = None,
) -> tuple[SeatHold, ProgramSession]:
    now = datetime.now(UTC)
    if ttl_seconds is None:
        ttl_seconds = config_service.seat_hold_ttl_seconds(db)
    session_obj = _lock_session(db, session_id)
    if session_obj is None or session_obj.status is SessionStatus.cancelled:
        raise SessionNotFound(str(session_id))

    _reclaim_expired(db, session_obj, now=now)

    # Anti-hoarding: cap a guardian's concurrent live holds (PRD fraud basics).
    # Counts unexpired browsing holds plus firm checkout reservations, across all
    # sessions, so a guardian can't pin seats by leaving carts mid-checkout.
    limit = config_service.max_active_holds_per_guardian(db)
    active_holds = (
        db.scalar(
            select(func.count(SeatHold.id)).where(
                SeatHold.held_by_id == held_by_id,
                or_(
                    and_(
                        SeatHold.status == SeatHoldStatus.active,
                        SeatHold.expires_at >= now,
                    ),
                    SeatHold.status == SeatHoldStatus.reserved,
                ),
            )
        )
        or 0
    )
    if active_holds >= limit:
        raise TooManyHolds(limit)

    if quantity > session_obj.seats_remaining:
        raise SoldOut(session_obj.seats_remaining)

    session_obj.seats_taken += quantity  # CHECK constraint is the backstop
    hold = SeatHold(
        session_id=session_obj.id,
        held_by_id=held_by_id,
        quantity=quantity,
        status=SeatHoldStatus.active,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    db.add(hold)
    db.flush()
    if session_obj.seats_taken >= session_obj.capacity:
        events_service.record(
            db, event_type="session_filled", props={"session_id": str(session_obj.id)}
        )
    return hold, session_obj


def reserve_hold(db: Session, *, hold_id: uuid.UUID) -> bool:
    """Convert an active browsing hold into a firm checkout reservation (ADR-0005).
    The seat stays counted but is no longer reclaimed by the TTL sweep; only an
    explicit terminal outcome (confirm/cancel/abandoned-sweep) resolves it.

    Takes the session lock and re-reads the hold under it, so a concurrent TTL
    reclaim can't expire the seat between the caller's check and this transition
    (that would strand a paid seat). Returns False if the seat was already lost.
    """
    hold = db.get(SeatHold, hold_id)
    if hold is None:
        return False
    _lock_session(db, hold.session_id)
    db.refresh(hold)
    if hold.status is not SeatHoldStatus.active:
        return False
    hold.status = SeatHoldStatus.reserved
    db.flush()
    return True


def release_hold(db: Session, *, hold_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    hold = db.get(SeatHold, hold_id)
    if hold is None or hold.held_by_id != actor_id:
        raise HoldNotFound(str(hold_id))
    # Lock the session, THEN re-read the hold, so two concurrent releasers can't both
    # pass the status guard and double-decrement seats_taken (INV-1).
    session_obj = _lock_session(db, hold.session_id)
    db.refresh(hold)
    if hold.status not in (SeatHoldStatus.active, SeatHoldStatus.reserved):
        return  # already released/expired/consumed — nothing to give back
    if session_obj is not None:
        session_obj.seats_taken -= hold.quantity
    hold.status = SeatHoldStatus.released
    db.flush()


def force_release(db: Session, *, hold_id: uuid.UUID) -> None:
    """Release a hold regardless of owner — for provider/admin session cancels and
    the abandoned-checkout sweep.

    Gives seats back for active (browsing), reserved (mid-checkout), and consumed
    (confirmed) holds. Locks the session first, then re-reads the hold under the lock,
    so concurrent releasers (e.g. a provider cancel racing the sweep) can't both
    decrement seats_taken for the same hold (INV-1).
    """
    hold = db.get(SeatHold, hold_id)
    if hold is None:
        return
    session_obj = _lock_session(db, hold.session_id)
    db.refresh(hold)
    if hold.status in (SeatHoldStatus.released, SeatHoldStatus.expired):
        return
    if session_obj is not None:
        session_obj.seats_taken -= hold.quantity
    hold.status = SeatHoldStatus.released
    db.flush()


def availability(db: Session, session_id: uuid.UUID) -> ProgramSession | None:
    """Live availability. Reclaims expired holds first so the number is honest."""
    session_obj = _lock_session(db, session_id)
    if session_obj is None:
        return None
    _reclaim_expired(db, session_obj, now=datetime.now(UTC))
    return session_obj
