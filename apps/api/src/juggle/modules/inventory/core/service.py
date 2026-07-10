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

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.catalog.core.models import Session as ProgramSession
from juggle.modules.catalog.core.models import SessionStatus
from juggle.modules.inventory.core.models import SeatHold, SeatHoldStatus

# TODO(M7): source the TTL from the config module (runtime-editable per PRD §10.1).
DEFAULT_HOLD_TTL_SECONDS = 900  # 15 minutes


class SessionNotFound(Exception):
    """No such session (or it is not holdable)."""


class SoldOut(Exception):
    """Not enough seats remain to satisfy the requested quantity."""

    def __init__(self, remaining: int) -> None:
        self.remaining = remaining
        super().__init__(f"only {remaining} seat(s) remaining")


class HoldNotFound(Exception):
    """No active hold with that id belonging to the caller."""


def _lock_session(db: Session, session_id: uuid.UUID) -> ProgramSession | None:
    return db.execute(
        select(ProgramSession).where(ProgramSession.id == session_id).with_for_update()
    ).scalar_one_or_none()


def _reclaim_expired(db: Session, session_obj: ProgramSession, *, now: datetime) -> None:
    """Release seats from active holds whose TTL has lapsed. Runs under the lock."""
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


def hold_seats(
    db: Session,
    *,
    session_id: uuid.UUID,
    held_by_id: uuid.UUID,
    quantity: int,
    ttl_seconds: int = DEFAULT_HOLD_TTL_SECONDS,
) -> tuple[SeatHold, ProgramSession]:
    now = datetime.now(UTC)
    session_obj = _lock_session(db, session_id)
    if session_obj is None or session_obj.status is SessionStatus.cancelled:
        raise SessionNotFound(str(session_id))

    _reclaim_expired(db, session_obj, now=now)

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
    return hold, session_obj


def release_hold(db: Session, *, hold_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    hold = db.get(SeatHold, hold_id)
    if hold is None or hold.held_by_id != actor_id:
        raise HoldNotFound(str(hold_id))
    if hold.status is not SeatHoldStatus.active:
        return  # already released/expired/consumed — nothing to give back
    session_obj = _lock_session(db, hold.session_id)
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
