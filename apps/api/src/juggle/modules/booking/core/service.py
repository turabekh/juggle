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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from juggle.modules.booking.core.models import Booking, BookingChild, BookingStatus
from juggle.modules.booking.core.schemas import (
    BookingChildOut,
    BookingOut,
    CheckoutChild,
    CheckoutItem,
    OrderOut,
    ProviderOrderSummary,
    SessionCancelResult,
    TaxInvoiceLine,
    TaxInvoiceOut,
    TaxInvoiceParty,
    TaxInvoiceTotals,
)
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.catalog.core.models import Program, SessionStatus, Venue
from juggle.modules.catalog.core.models import Session as CatalogSession
from juggle.modules.config.core import service as config_service
from juggle.modules.events.core import service as events_service
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
from juggle.settings import get_settings

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


class NotOrgMember(Exception):
    """Actor is not a member of the organisation (tax-invoice access)."""


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


def _charged_quantity(db: Session, booking: Booking) -> int:
    """Seats charged at checkout for this booking — the immutable hold quantity, not a
    live child count (a child deleted post-checkout must not under-accrue; ADR-0005 §6)."""
    if booking.seat_hold_id is not None:
        hold = db.get(SeatHold, booking.seat_hold_id)
        if hold is not None:
            return hold.quantity
    return db.scalar(
        select(func.count(BookingChild.id)).where(BookingChild.booking_id == booking.id)
    ) or 0


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


def _order_view(
    db: Session, payment: Payment, *, client_secret: str | None = None
) -> OrderOut:
    return OrderOut(
        payment_id=payment.id,
        amount_cents=payment.amount_cents,
        application_fee_cents=payment.application_fee_cents,
        fee_gst_cents=payment.fee_gst_cents,
        currency=payment.currency,
        status=payment.status.value,
        client_secret=client_secret,
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
    # Children may belong to the actor or any of their co-guardians (PRD §7.3).
    family_ids = identity_service.family_guardian_ids(db, guardian_id)
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
            if child is None or child.guardian_id not in family_ids:
                raise ChildInvalid(str(child_input.child_id))
            age = _age_at(child.date_of_birth, session.starts_at)
            if not (session.age_min <= age <= session.age_max):
                raise AgeOutOfRange(str(child_input.child_id))

        total += session.price_cents * hold.quantity
        prepared.append((hold, session, program, item.children))

    # Firm every seat BEFORE talking to Stripe (ADR-0005 §1): a reserved hold counts
    # against capacity but is no longer reclaimed by the TTL sweep, so a reclaim during
    # the payment round-trip can't strand a paid seat. reserve_hold locks the session and
    # re-checks under the lock; a False means the seat was lost between hold and checkout.
    checkout_window = config_service.checkout_window_seconds(db)
    for hold, _session, _program, _children in prepared:
        if not inventory_service.reserve_hold(db, hold_id=hold.id):
            raise HoldExpired(str(hold.id))
        # expires_at becomes the checkout deadline the abandoned-checkout sweep reads.
        hold.expires_at = now + timedelta(seconds=checkout_window)

    # Per-session rounding of the take-rate so the parts sum to the charge (ADR-0002).
    fee_rate = config_service.platform_fee_rate(db)
    gst_rate = config_service.gst_rate(db)
    fee_total = 0
    gst_total = 0
    for hold, session, _program, _children in prepared:
        line = session.price_cents * hold.quantity
        fee, gst, _net = payments_service.take_rate(line, fee_rate, gst_rate)
        fee_total += fee
        gst_total += gst

    payment, intent = payments_service.create_payment(
        db,
        guardian_id=guardian_id,
        amount_cents=total,
        application_fee_cents=fee_total,
        fee_gst_cents=gst_total,
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

    db.flush()
    events_service.record(
        db,
        event_type="checkout_started",
        props={"payment_id": str(payment.id), "sessions": len(prepared)},
    )
    return _order_view(db, payment, client_secret=intent.client_secret)


def _settle_confirmed(db: Session, payment: Payment, *, email_gateway: EmailGateway) -> None:
    """Record an already-succeeded payment as a confirmed order: consume the reserved
    seats, email the confirmation, and accrue each provider's payout. Shared by the
    synchronous confirm endpoint and the payment_intent.succeeded webhook (ADR-0005)."""
    payments_service.mark_succeeded(db, payment)
    events_service.record(
        db, event_type="checkout_completed", props={"payment_id": str(payment.id)}
    )
    for booking in _bookings_for_payment(db, payment.id):
        booking.status = BookingStatus.confirmed
        if booking.seat_hold_id is not None:
            hold = db.get(SeatHold, booking.seat_hold_id)
            if hold is not None and hold.status in (
                SeatHoldStatus.active,
                SeatHoldStatus.reserved,
            ):
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

    # Accrue each provider's net earnings to a payout, due after the session runs.
    # Accrue on the CHARGED quantity (the hold), not a live child count, so a child
    # deleted between checkout and confirm cannot under-accrue (ADR-0005 §6).
    delay_days = config_service.payout_delay_days(db)
    fee_rate = config_service.platform_fee_rate(db)
    gst_rate = config_service.gst_rate(db)
    for booking in _bookings_for_payment(db, payment.id):
        session_obj = db.get(CatalogSession, booking.session_id)
        if session_obj is None:
            continue
        quantity = _charged_quantity(db, booking)
        gross = booking.unit_price_cents * quantity
        fee, gst, net = payments_service.take_rate(gross, fee_rate, gst_rate)
        payout = payments_service.accrue_payout(
            db,
            organisation_id=booking.organisation_id,
            session_id=session_obj.id,
            net_cents=net,
            scheduled_for=session_obj.ends_at + timedelta(days=delay_days),
        )
        # Persist the full money split + the payout it fed, so a later refund claws back
        # this amount from this payout and the provider tax invoice itemises the exact
        # commission/GST charged — immune to config drift or a shared session payout.
        booking.commission_cents = fee
        booking.commission_gst_cents = gst
        booking.accrued_net_cents = net
        booking.payout_id = payout.id


def confirm(
    db: Session,
    *,
    payment_id: uuid.UUID,
    guardian_id: uuid.UUID,
    email_gateway: EmailGateway,
) -> OrderOut:
    """Synchronous confirm — FakeGateway/test path only (ADR-0005 §5). Real Stripe
    confirmation is webhook-driven via ``settle_payment_succeeded``.

    Row-lock the payment so a concurrent abandoned-sweep can't flip it to failed on a
    stale read after we've decided to confirm (ADR-0005 §3). Under the lock the status
    is authoritative: if the sweep already failed it, the pending guard below rejects."""
    payment = payments_service.get_payment_for_update(db, payment_id)
    if payment is None or payment.guardian_id != guardian_id:
        raise PaymentNotFound(str(payment_id))
    if payment.status is PaymentStatus.succeeded:
        return _order_view(db, payment)
    if payment.status is not PaymentStatus.pending:
        raise PaymentNotPending(str(payment_id))

    _settle_confirmed(db, payment, email_gateway=email_gateway)
    return _order_view(db, payment)


def _reservation_is_firm(db: Session, payment: Payment) -> bool:
    """Is every seat for this order still firmly reserved? False if any booking was
    cancelled/refunded, its session cancelled, or its hold released (the seat is gone)."""
    for booking in _bookings_for_payment(db, payment.id):
        if booking.status not in (BookingStatus.pending, BookingStatus.confirmed):
            return False
        session_obj = db.get(CatalogSession, booking.session_id)
        if session_obj is None or session_obj.status is SessionStatus.cancelled:
            return False
        if booking.seat_hold_id is not None:
            hold = db.get(SeatHold, booking.seat_hold_id)
            if hold is None or hold.status not in (
                SeatHoldStatus.active,
                SeatHoldStatus.reserved,
                SeatHoldStatus.consumed,
            ):
                return False
    return True


def _auto_refund_lost_seat(
    db: Session, payment: Payment, *, gateway: PaymentGateway, email_gateway: EmailGateway
) -> None:
    """The charge succeeded but the seat is gone (session cancelled / order already
    settled elsewhere) — refund in full, release any residual seats, notify (ADR-0005 §3)."""
    payments_service.refund(db, payment, gateway=gateway)
    for booking in _bookings_for_payment(db, payment.id):
        if booking.seat_hold_id is not None:
            inventory_service.force_release(db, hold_id=booking.seat_hold_id)
        booking.status = BookingStatus.refunded
    db.flush()
    guardian = identity_service.get_user(db, payment.guardian_id)
    if guardian is not None:
        notifications_service.notify_seat_unavailable_refund(
            db,
            user_id=guardian.id,
            to_email=guardian.email,
            total_cents=payment.amount_cents,
            gateway=email_gateway,
        )
    events_service.record(
        db, event_type="checkout_seat_lost_refunded", props={"payment_id": str(payment.id)}
    )


def settle_payment_succeeded(
    db: Session, *, intent_id: str, gateway: PaymentGateway, email_gateway: EmailGateway
) -> None:
    """payment_intent.succeeded: the source of truth for confirmation (ADR-0005 §3).
    Row-locks the payment, then confirms if the reservation is still firm, else
    auto-refunds the lost seat. Idempotent on redelivery."""
    payment = payments_service.get_payment_by_intent(db, intent_id, for_update=True)
    if payment is None or payment.status in (
        PaymentStatus.succeeded,
        PaymentStatus.refunded,
    ):
        return  # unknown PI, or already settled/refunded — nothing to do
    if payment.status is PaymentStatus.pending and _reservation_is_firm(db, payment):
        _settle_confirmed(db, payment, email_gateway=email_gateway)
    else:
        _auto_refund_lost_seat(db, payment, gateway=gateway, email_gateway=email_gateway)


def settle_payment_canceled(db: Session, *, intent_id: str) -> None:
    """payment_intent.canceled: a terminal outcome — release the seats and fail the
    order (ADR-0005 §4). Idempotent; a non-pending payment is left untouched."""
    payment = payments_service.get_payment_by_intent(db, intent_id, for_update=True)
    if payment is None or payment.status is not PaymentStatus.pending:
        return
    for booking in _bookings_for_payment(db, payment.id):
        booking.status = BookingStatus.cancelled
        if booking.seat_hold_id is not None:
            inventory_service.force_release(db, hold_id=booking.seat_hold_id)
    payments_service.mark_failed(db, payment)
    db.flush()
    events_service.record(
        db, event_type="checkout_canceled", props={"payment_id": str(payment.id)}
    )


def handle_stripe_webhook(
    db: Session,
    *,
    payload: bytes,
    sig_header: str,
    secret: str,
    gateway: PaymentGateway,
    email_gateway: EmailGateway,
) -> str:
    """The single Stripe webhook sink. Verifies the raw-body signature and dedupes via
    the stripe_event ledger (both payments primitives), then dispatches: account.updated
    → payments (Connect flags); payment_intent.* → order settlement. One transaction per
    event (INV-2); payment_failed is non-terminal (ADR-0005 §4)."""
    event = payments_service.verify_event(payload, sig_header, secret)
    if not payments_service.record_event(db, event.id, event.type):
        return "duplicate"
    obj = event.data_object
    if event.type == "account.updated":
        payments_service.apply_account_updated(
            db,
            account_id=str(obj["id"]),
            charges_enabled=bool(obj["charges_enabled"]),
            payouts_enabled=bool(obj["payouts_enabled"]),
        )
    elif event.type == "payment_intent.succeeded":
        settle_payment_succeeded(
            db, intent_id=str(obj["id"]), gateway=gateway, email_gateway=email_gateway
        )
    elif event.type == "payment_intent.canceled":
        settle_payment_canceled(db, intent_id=str(obj["id"]))
    return "ok"


def cancel(db: Session, *, payment_id: uuid.UUID, guardian_id: uuid.UUID) -> OrderOut:
    payment = payments_service.get_payment_for_update(db, payment_id)
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
    events_service.record(
        db, event_type="booking_cancelled", props={"payment_id": str(payment.id)}
    )
    return _order_view(db, payment)


def sweep_abandoned_checkouts(
    db: Session, *, gateway: PaymentGateway, now: datetime | None = None
) -> int:
    """Terminal outcome for checkouts that never completed (ADR-0005 §1): for each
    pending payment older than the checkout window, hard-cancel the PaymentIntent (so a
    late webhook can't strand the seat), free the reserved seats, and fail the order.

    This is the ONLY reclaimer of a firm reservation — the TTL sweep deliberately skips
    reserved holds — so it is load-bearing and idempotent (a re-run finds nothing pending).
    """
    moment = now or datetime.now(UTC)
    deadline = moment - timedelta(seconds=config_service.checkout_window_seconds(db))
    # FOR UPDATE SKIP LOCKED so concurrent ticks don't double-sweep. A payment being
    # confirmed/cancelled right now takes its own FOR UPDATE on the row (confirm/cancel),
    # so either this sweep skips it (already locked) or that path blocks on our lock and
    # then sees `failed` and rejects — the confirm-vs-settle race is serialised (ADR-0005 §3).
    stale = db.scalars(
        select(Payment)
        .where(
            Payment.status == PaymentStatus.pending,
            Payment.created_at < deadline,
        )
        .with_for_update(skip_locked=True)
    ).all()
    swept = 0
    for payment in stale:
        if payment.stripe_payment_intent_id is not None:
            gateway.cancel_payment_intent(payment.stripe_payment_intent_id)
        for booking in _bookings_for_payment(db, payment.id):
            booking.status = BookingStatus.cancelled
            if booking.seat_hold_id is not None:
                inventory_service.force_release(db, hold_id=booking.seat_hold_id)
        payments_service.mark_failed(db, payment)
        events_service.record(
            db, event_type="checkout_abandoned", props={"payment_id": str(payment.id)}
        )
        swept += 1
    db.flush()
    return swept


def list_bookings(db: Session, guardian_id: uuid.UUID) -> list[BookingOut]:
    # A family sees each other's bookings (PRD §7.3).
    family_ids = identity_service.family_guardian_ids(db, guardian_id)
    bookings = db.scalars(
        select(Booking)
        .where(Booking.guardian_id.in_(family_ids))
        .order_by(Booking.created_at.desc())
    ).all()
    return [_booking_out(db, b) for b in bookings]


def _clawback_booking(db: Session, booking: Booking, *, gateway: PaymentGateway) -> None:
    """Reverse exactly the net this booking accrued out of exactly the payout it fed
    (ADR-0005 §7). Uses the persisted ``accrued_net_cents``/``payout_id`` — no recomputation
    (config-drift-proof) and no per-session guessing (multi-payout-proof)."""
    if booking.payout_id is None or booking.accrued_net_cents <= 0:
        return
    payments_service.adjust_payout_for_refund(
        db,
        payout_id=booking.payout_id,
        net_cents=booking.accrued_net_cents,
        gateway=gateway,
        idempotency_key=f"rev-{booking.id}",
    )


def provider_orders(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> list[ProviderOrderSummary]:
    """The org's invoiceable orders (each with a confirmed booking), newest first — the
    list a provider picks from to open a tax invoice. Member-gated."""
    if org_service.get_member(db, organisation_id, actor_id) is None:
        raise NotOrgMember(str(organisation_id))
    bookings = db.scalars(
        select(Booking).where(
            Booking.organisation_id == organisation_id,
            Booking.status == BookingStatus.confirmed,
            Booking.payment_id.is_not(None),
        )
    ).all()
    by_payment: dict[uuid.UUID, list[Booking]] = {}
    for booking in bookings:
        assert booking.payment_id is not None
        by_payment.setdefault(booking.payment_id, []).append(booking)

    summaries: list[ProviderOrderSummary] = []
    for payment_id, order_bookings in by_payment.items():
        payment = payments_service.get_payment(db, payment_id)
        if payment is None:
            continue
        summaries.append(
            ProviderOrderSummary(
                payment_id=payment_id,
                ordered_at=payment.created_at,
                session_count=len(order_bookings),
                gross_cents=sum(
                    b.commission_cents + b.commission_gst_cents + b.accrued_net_cents
                    for b in order_bookings
                ),
                commission_cents=sum(b.commission_cents for b in order_bookings),
                commission_gst_cents=sum(b.commission_gst_cents for b in order_bookings),
                net_cents=sum(b.accrued_net_cents for b in order_bookings),
            )
        )
    summaries.sort(key=lambda s: s.ordered_at, reverse=True)
    return summaries


def provider_tax_invoice(
    db: Session, *, payment_id: uuid.UUID, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> TaxInvoiceOut:
    """Provider-facing tax invoice for the platform's commission on one order (ADR-0002,
    §8.4). The supplier is the platform (commission + GST — the taxable supply); the
    recipient is the provider. Itemises only THIS org's confirmed lines in the order, using
    the money split persisted at confirm. Member-gated."""
    if org_service.get_member(db, organisation_id, actor_id) is None:
        raise NotOrgMember(str(organisation_id))
    payment = payments_service.get_payment(db, payment_id)
    if payment is None:
        raise PaymentNotFound(str(payment_id))
    org = org_service.get_organisation(db, organisation_id)

    lines: list[TaxInvoiceLine] = []
    tot_gross = tot_fee = tot_gst = tot_net = 0
    for booking in _bookings_for_payment(db, payment.id):
        if booking.organisation_id != organisation_id:
            continue
        if booking.status is not BookingStatus.confirmed:
            continue  # refunded/cancelled lines are not a standing taxable supply
        session_obj = db.get(CatalogSession, booking.session_id)
        if session_obj is None:
            continue
        program = db.get(Program, session_obj.program_id)
        gross = booking.commission_cents + booking.commission_gst_cents + booking.accrued_net_cents
        lines.append(
            TaxInvoiceLine(
                session_id=booking.session_id,
                session_title=program.title if program is not None else "Session",
                starts_at=session_obj.starts_at,
                status=booking.status.value,
                gross_cents=gross,
                commission_cents=booking.commission_cents,
                commission_gst_cents=booking.commission_gst_cents,
                net_cents=booking.accrued_net_cents,
            )
        )
        tot_gross += gross
        tot_fee += booking.commission_cents
        tot_gst += booking.commission_gst_cents
        tot_net += booking.accrued_net_cents

    if not lines:
        raise PaymentNotFound(str(payment_id))  # this org has no invoiceable line in the order

    settings = get_settings()
    return TaxInvoiceOut(
        invoice_number=f"INV-{str(payment.id)[:8]}-{str(organisation_id)[:8]}".upper(),
        issued_at=datetime.now(UTC),
        payment_id=payment.id,
        currency=payment.currency,
        supplier=TaxInvoiceParty(
            name=settings.platform_legal_name, abn=settings.platform_abn or None
        ),
        recipient=TaxInvoiceParty(
            name=org.name if org is not None else "", abn=org.abn if org is not None else None
        ),
        lines=lines,
        totals=TaxInvoiceTotals(
            gross_cents=tot_gross,
            commission_cents=tot_fee,
            commission_gst_cents=tot_gst,
            net_cents=tot_net,
        ),
    )


def refund_order(
    db: Session, *, payment_id: uuid.UUID, gateway: PaymentGateway
) -> OrderOut:
    """Refund a whole order (admin bookings-console action): refund the payment, claw back
    every booking's payout, release every seat, and mark the bookings refunded. Idempotent."""
    payment = payments_service.get_payment_for_update(db, payment_id)
    if payment is None:
        raise PaymentNotFound(str(payment_id))
    if payment.status is PaymentStatus.refunded:
        return _order_view(db, payment)

    if payment.status in (PaymentStatus.succeeded, PaymentStatus.partially_refunded):
        payments_service.refund(db, payment, gateway=gateway)  # full remaining
        for booking in _bookings_for_payment(db, payment.id):
            if booking.status is not BookingStatus.refunded:
                _clawback_booking(db, booking, gateway=gateway)
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

    # Refund ONLY this session's portion of each order (a cart may span other sessions
    # that still stand): refund the cancelled bookings' line total, claw back their payouts.
    refunded_payment_ids: set[uuid.UUID] = set()
    for booking in bookings:
        if booking.payment_id is None:
            continue
        payment = payments_service.get_payment_for_update(db, booking.payment_id)
        if payment is None:
            continue
        if payment.status in (PaymentStatus.succeeded, PaymentStatus.partially_refunded):
            line = booking.unit_price_cents * _charged_quantity(db, booking)
            payments_service.refund(db, payment, gateway=gateway, amount_cents=line)
            _clawback_booking(db, booking, gateway=gateway)
            refunded_payment_ids.add(booking.payment_id)
        elif payment.status is PaymentStatus.pending:
            payments_service.mark_failed(db, payment)
    refunded = len(refunded_payment_ids)

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
