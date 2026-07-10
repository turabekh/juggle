"""Booking service — the checkout orchestrator (PRD §7.4).

Booking sits at the top of the transactions layer, so it composes the lower
modules through their services/models: catalog (session price/age), identity
(child ownership + age), inventory (seat holds), and payments (the gateway).

State machine per cart:

    hold(s) held  ──checkout──▶  payment=pending, bookings=pending (hold active)
                                     │                     │
                              confirm│                cancel│
                                     ▼                     ▼
        payment=succeeded, bookings=confirmed,   payment=failed, bookings=cancelled,
        holds=consumed (seats stay)              holds released (seats freed)

Idempotency is at the cart level via ``payment.idempotency_key``: a repeated
checkout with the same key returns the original order instead of re-charging.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.booking.core.models import Booking, BookingChild, BookingStatus
from juggle.modules.booking.core.schemas import (
    BookingChildOut,
    BookingOut,
    CheckoutChild,
    CheckoutItem,
    OrderOut,
    SessionCancelResult,
)
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.catalog.core.models import Program, SessionStatus, Venue
from juggle.modules.catalog.core.models import Session as CatalogSession
from juggle.modules.config.core import service as config_service
from juggle.modules.identity.core import service as identity_service
from juggle.modules.identity.core.models import Child
from juggle.modules.inventory.core import service as inventory_service
from juggle.modules.inventory.core.models import SeatHold, SeatHoldStatus
from juggle.modules.notifications.core import service as notifications_service
from juggle.modules.notifications.core.gateway import EmailGateway
from juggle.modules.notifications.core.schemas import ConfirmationSession
from juggle.modules.org.core import service as org_service
from juggle.modules.org.core.models import OrgRole
from juggle.modules.payments.core import service as payments_service
from juggle.modules.payments.core.gateway import PaymentGateway
from juggle.modules.payments.core.models import Payment, PaymentStatus

# The seat-hold window is extended to cover the payment step so a pending
# booking's seats aren't reclaimed mid-checkout. TODO(M7): source from config.
CHECKOUT_WINDOW_SECONDS = 1200  # 20 minutes


class EmptyCart(Exception):
    """Checkout was called with no items."""


class HoldInvalid(Exception):
    """Hold missing, not owned by the caller, not active, or session unavailable."""


class HoldExpired(Exception):
    """The seat hold's TTL lapsed before checkout."""


class ChildCountMismatch(Exception):
    """Number of children does not match the seats held."""


class ChildInvalid(Exception):
    """Child missing or not owned by the guardian."""


class AgeOutOfRange(Exception):
    """Child's age falls outside the session's age band (PRD §7.2)."""


class PaymentNotFound(Exception):
    """No such payment for this guardian."""


class PaymentNotPending(Exception):
    """Payment has already been finalised (succeeded/failed)."""


class SessionNotFound(Exception):
    """No such session."""


class NotSessionOwner(Exception):
    """Actor is not an owner of the organisation that runs this session."""


def _age_at(dob: date, at: datetime) -> int:
    on = at.date()
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def _booking_out(db: Session, booking: Booking) -> BookingOut:
    children = db.scalars(
        select(BookingChild).where(BookingChild.booking_id == booking.id)
    ).all()
    return BookingOut(
        id=booking.id,
        session_id=booking.session_id,
        organisation_id=booking.organisation_id,
        payment_id=booking.payment_id,
        status=booking.status.value,
        unit_price_cents=booking.unit_price_cents,
        children=[
            BookingChildOut(child_id=c.child_id, form_answers=c.form_answers) for c in children
        ],
    )


def _bookings_for_payment(db: Session, payment_id: uuid.UUID) -> list[Booking]:
    return list(
        db.scalars(
            select(Booking).where(Booking.payment_id == payment_id).order_by(Booking.created_at)
        )
    )


def _child_names(db: Session, booking_id: uuid.UUID) -> list[str]:
    names: list[str] = []
    for link in db.scalars(select(BookingChild).where(BookingChild.booking_id == booking_id)):
        child = db.get(Child, link.child_id)
        if child is not None:
            names.append(child.first_name)
    return names


def _confirmation_sessions(db: Session, payment_id: uuid.UUID) -> list[ConfirmationSession]:
    """Structured booked-session data for confirmations / calendar files."""
    out: list[ConfirmationSession] = []
    for booking in _bookings_for_payment(db, payment_id):
        session_obj = db.get(CatalogSession, booking.session_id)
        if session_obj is None:
            continue
        program = db.get(Program, session_obj.program_id)
        venue = db.get(Venue, session_obj.venue_id)
        out.append(
            ConfirmationSession(
                session_id=session_obj.id,
                title=program.title if program is not None else "Session",
                starts_at=session_obj.starts_at,
                ends_at=session_obj.ends_at,
                venue_name=venue.name if venue is not None else "",
                children=_child_names(db, booking.id),
            )
        )
    return out


def order_calendar(db: Session, *, payment_id: uuid.UUID, guardian_id: uuid.UUID) -> str:
    """The .ics for a guardian's own order (PRD §7.4 add-to-calendar)."""
    payment = payments_service.get_payment(db, payment_id)
    if payment is None or payment.guardian_id != guardian_id:
        raise PaymentNotFound(str(payment_id))
    return notifications_service.order_ics(_confirmation_sessions(db, payment.id))


def _order_view(db: Session, payment: Payment) -> OrderOut:
    return OrderOut(
        payment_id=payment.id,
        amount_cents=payment.amount_cents,
        application_fee_cents=payment.application_fee_cents,
        currency=payment.currency,
        status=payment.status.value,
        bookings=[_booking_out(db, b) for b in _bookings_for_payment(db, payment.id)],
    )


def checkout(
    db: Session,
    *,
    guardian_id: uuid.UUID,
    idempotency_key: str,
    items: list[CheckoutItem],
    gateway: PaymentGateway,
) -> OrderOut:
    if not items:
        raise EmptyCart()

    existing = payments_service.find_by_idempotency_key(
        db, guardian_id=guardian_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        return _order_view(db, existing)

    now = datetime.now(UTC)
    prepared: list[tuple[SeatHold, CatalogSession, Program, list[CheckoutChild]]] = []
    total = 0

    for item in items:
        hold = db.get(SeatHold, item.hold_id)
        if (
            hold is None
            or hold.held_by_id != guardian_id
            or hold.status is not SeatHoldStatus.active
        ):
            raise HoldInvalid(str(item.hold_id))
        if hold.expires_at < now:
            raise HoldExpired(str(item.hold_id))
        if len(item.children) != hold.quantity:
            raise ChildCountMismatch(str(item.hold_id))

        session = db.get(CatalogSession, hold.session_id)
        if session is None or session.status is SessionStatus.cancelled:
            raise HoldInvalid(str(item.hold_id))
        program = db.get(Program, session.program_id)
        if program is None:
            raise HoldInvalid(str(item.hold_id))

        for child_input in item.children:
            child = db.get(Child, child_input.child_id)
            if child is None or child.guardian_id != guardian_id:
                raise ChildInvalid(str(child_input.child_id))
            age = _age_at(child.date_of_birth, session.starts_at)
            if not (session.age_min <= age <= session.age_max):
                raise AgeOutOfRange(str(child_input.child_id))

        total += session.price_cents * hold.quantity
        prepared.append((hold, session, program, item.children))

    payment = payments_service.create_payment(
        db,
        guardian_id=guardian_id,
        amount_cents=total,
        idempotency_key=idempotency_key,
        gateway=gateway,
    )

    for hold, session, program, children in prepared:
        booking = Booking(
            session_id=session.id,
            guardian_id=guardian_id,
            organisation_id=program.organisation_id,
            payment_id=payment.id,
            seat_hold_id=hold.id,
            status=BookingStatus.pending,
            unit_price_cents=session.price_cents,
        )
        db.add(booking)
        db.flush()
        for child_input in children:
            db.add(
                BookingChild(
                    booking_id=booking.id,
                    child_id=child_input.child_id,
                    form_answers=child_input.form_answers,
                )
            )
        # Extend the hold to cover the payment step (see module docstring).
        hold.expires_at = now + timedelta(seconds=config_service.checkout_window_seconds(db))

    db.flush()
    return _order_view(db, payment)


def confirm(
    db: Session,
    *,
    payment_id: uuid.UUID,
    guardian_id: uuid.UUID,
    gateway: PaymentGateway,
    email_gateway: EmailGateway,
) -> OrderOut:
    payment = payments_service.get_payment(db, payment_id)
    if payment is None or payment.guardian_id != guardian_id:
        raise PaymentNotFound(str(payment_id))
    if payment.status is PaymentStatus.succeeded:
        return _order_view(db, payment)
    if payment.status is not PaymentStatus.pending:
        raise PaymentNotPending(str(payment_id))

    payments_service.mark_succeeded(db, payment, gateway=gateway)
    for booking in _bookings_for_payment(db, payment.id):
        booking.status = BookingStatus.confirmed
        if booking.seat_hold_id is not None:
            hold = db.get(SeatHold, booking.seat_hold_id)
            if hold is not None and hold.status is SeatHoldStatus.active:
                hold.status = SeatHoldStatus.consumed
    db.flush()

    # Confirmation email + calendar invite (once, on the pending→succeeded edge).
    guardian = identity_service.get_user(db, payment.guardian_id)
    if guardian is not None:
        notifications_service.notify_booking_confirmation(
            db,
            user_id=guardian.id,
            to_email=guardian.email,
            sessions=_confirmation_sessions(db, payment.id),
            total_cents=payment.amount_cents,
            gateway=email_gateway,
        )
    return _order_view(db, payment)


def cancel(db: Session, *, payment_id: uuid.UUID, guardian_id: uuid.UUID) -> OrderOut:
    payment = payments_service.get_payment(db, payment_id)
    if payment is None or payment.guardian_id != guardian_id:
        raise PaymentNotFound(str(payment_id))
    if payment.status is PaymentStatus.failed:
        return _order_view(db, payment)
    if payment.status is not PaymentStatus.pending:
        raise PaymentNotPending(str(payment_id))

    for booking in _bookings_for_payment(db, payment.id):
        booking.status = BookingStatus.cancelled
        if booking.seat_hold_id is not None:
            try:
                inventory_service.release_hold(
                    db, hold_id=booking.seat_hold_id, actor_id=guardian_id
                )
            except inventory_service.HoldNotFound:
                pass  # already released/expired — seats already accounted for
    payments_service.mark_failed(db, payment)
    db.flush()
    return _order_view(db, payment)


def list_bookings(db: Session, guardian_id: uuid.UUID) -> list[BookingOut]:
    bookings = db.scalars(
        select(Booking)
        .where(Booking.guardian_id == guardian_id)
        .order_by(Booking.created_at.desc())
    ).all()
    return [_booking_out(db, b) for b in bookings]


def refund_order(
    db: Session, *, payment_id: uuid.UUID, gateway: PaymentGateway
) -> OrderOut:
    """Refund a whole order (admin bookings-console action): refund the payment,
    release every seat, and mark the bookings refunded. Idempotent."""
    payment = payments_service.get_payment(db, payment_id)
    if payment is None:
        raise PaymentNotFound(str(payment_id))
    if payment.status is PaymentStatus.refunded:
        return _order_view(db, payment)

    if payment.status is PaymentStatus.succeeded:
        payments_service.refund(db, payment, gateway=gateway)
    elif payment.status is PaymentStatus.pending:
        payments_service.mark_failed(db, payment)

    for booking in _bookings_for_payment(db, payment.id):
        if booking.seat_hold_id is not None:
            inventory_service.force_release(db, hold_id=booking.seat_hold_id)
        booking.status = BookingStatus.refunded
    db.flush()
    return _order_view(db, payment)


def cancel_session(
    db: Session,
    *,
    session_id: uuid.UUID,
    actor_id: uuid.UUID,
    gateway: PaymentGateway,
    email_gateway: EmailGateway,
) -> SessionCancelResult:
    """Provider-initiated session cancellation (PRD §8.3): cancel the session,
    refund paid families, release all seats, dent reliability, notify families."""
    session = catalog_service.get_session(db, session_id)
    if session is None:
        raise SessionNotFound(str(session_id))
    program = catalog_service.get_program(db, session.program_id)
    if program is None:
        raise SessionNotFound(str(session_id))

    member = org_service.get_member(db, program.organisation_id, actor_id)
    if member is None or member.role is not OrgRole.owner:
        raise NotSessionOwner(str(session_id))

    org = org_service.get_organisation(db, program.organisation_id)
    current_score = org.reliability_score if org is not None else 0.0
    if session.status is SessionStatus.cancelled:
        return SessionCancelResult(
            session_id=session_id,
            cancelled_bookings=0,
            refunded_payments=0,
            reliability_score=current_score,
        )

    session.status = SessionStatus.cancelled
    bookings = list(
        db.scalars(
            select(Booking).where(
                Booking.session_id == session_id,
                Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed]),
            )
        )
    )

    # Refund each distinct paid payment once; fail still-pending ones.
    refunded = 0
    for payment_id in {b.payment_id for b in bookings if b.payment_id is not None}:
        payment = payments_service.get_payment(db, payment_id)
        if payment is None:
            continue
        if payment.status is PaymentStatus.succeeded:
            payments_service.refund(db, payment, gateway=gateway)
            refunded += 1
        elif payment.status is PaymentStatus.pending:
            payments_service.mark_failed(db, payment)

    for booking in bookings:
        if booking.seat_hold_id is not None:
            inventory_service.force_release(db, hold_id=booking.seat_hold_id)
        was_confirmed = booking.status is BookingStatus.confirmed
        booking.status = BookingStatus.refunded if was_confirmed else BookingStatus.cancelled
        guardian = identity_service.get_user(db, booking.guardian_id)
        if guardian is not None:
            notifications_service.notify_session_cancellation(
                db,
                user_id=guardian.id,
                to_email=guardian.email,
                session_title=program.title,
                starts_at=session.starts_at,
                refunded=was_confirmed,
                gateway=email_gateway,
            )

    updated = org_service.adjust_reliability(
        db, program.organisation_id, -config_service.reliability_cancellation_penalty(db)
    )
    db.flush()
    return SessionCancelResult(
        session_id=session_id,
        cancelled_bookings=len(bookings),
        refunded_payments=refunded,
        reliability_score=updated.reliability_score if updated is not None else current_score,
    )
