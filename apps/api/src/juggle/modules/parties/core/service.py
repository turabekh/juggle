"""Parties service (Milestone B1): the instant-book supply side — provider packages
and their capacity-1 slots. No money here; the deposit/balance/adjustment flow (B2–B4)
lands through the ``payments`` module.

Parties sits above payments in the layering, so it composes catalog (venue) and org
(membership) through their services.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.config.core import service as config_service
from juggle.modules.org.core import service as org_service
from juggle.modules.parties.core.models import (
    PartyBooking,
    PartyBookingStatus,
    PartyPackage,
    PartyPackageStatus,
    PartySlot,
    PartySlotStatus,
)
from juggle.modules.parties.core.schemas import PackageCreate, SlotCreate
from juggle.modules.payments.core import service as payments_service
from juggle.modules.payments.core.gateway import PaymentGateway, PaymentIntentResult
from juggle.modules.payments.core.models import Payment, PaymentPurpose, PaymentStatus


class NotOrgMember(Exception):
    """Caller is not a member of the organisation."""


class VenueNotFound(Exception):
    """No such venue, or it does not belong to this organisation."""


class PackageNotFound(Exception):
    """No such party package."""


class InvalidHeadcountBand(Exception):
    """max_headcount is below min_headcount."""


class SlotNotFound(Exception):
    """No such party slot."""


class SlotUnavailable(Exception):
    """The slot is already held/booked (capacity-1)."""


class HeadcountOutOfBand(Exception):
    """Requested headcount is outside the package's min/max."""


class PartyBookingNotFound(Exception):
    """No such party booking."""


def _require_member(db: Session, org_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    if org_service.get_member(db, org_id, actor_id) is None:
        raise NotOrgMember(str(org_id))


def create_package(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID, data: PackageCreate
) -> PartyPackage:
    _require_member(db, organisation_id, actor_id)
    if data.max_headcount < data.min_headcount:
        raise InvalidHeadcountBand(f"{data.max_headcount} < {data.min_headcount}")
    venue = catalog_service.get_venue(db, data.venue_id)
    if venue is None or venue.organisation_id != organisation_id:
        raise VenueNotFound(str(data.venue_id))
    package = PartyPackage(
        organisation_id=organisation_id,
        venue_id=data.venue_id,
        name=data.name,
        description=data.description,
        per_head_price_cents=data.per_head_price_cents,
        min_headcount=data.min_headcount,
        max_headcount=data.max_headcount,
        deposit_pct=data.deposit_pct,
        outdoor=data.outdoor,
    )
    db.add(package)
    db.flush()
    return package


def get_package(db: Session, package_id: uuid.UUID) -> PartyPackage | None:
    return db.get(PartyPackage, package_id)


def list_org_packages(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> list[PartyPackage]:
    """All of an org's party packages (member-gated, any status)."""
    _require_member(db, organisation_id, actor_id)
    return list(
        db.scalars(
            select(PartyPackage)
            .where(PartyPackage.organisation_id == organisation_id)
            .order_by(PartyPackage.created_at)
        )
    )


def list_active_packages(db: Session, organisation_id: uuid.UUID) -> list[PartyPackage]:
    """Public: an org's bookable party packages."""
    return list(
        db.scalars(
            select(PartyPackage)
            .where(
                PartyPackage.organisation_id == organisation_id,
                PartyPackage.status == PartyPackageStatus.active,
            )
            .order_by(PartyPackage.created_at)
        )
    )


def archive_package(
    db: Session, *, package_id: uuid.UUID, actor_id: uuid.UUID
) -> PartyPackage:
    package = db.get(PartyPackage, package_id)
    if package is None:
        raise PackageNotFound(str(package_id))
    _require_member(db, package.organisation_id, actor_id)
    package.status = PartyPackageStatus.archived
    db.flush()
    return package


def add_slots(
    db: Session, *, package_id: uuid.UUID, actor_id: uuid.UUID, slots: list[SlotCreate]
) -> list[PartySlot]:
    package = db.get(PartyPackage, package_id)
    if package is None:
        raise PackageNotFound(str(package_id))
    _require_member(db, package.organisation_id, actor_id)
    created: list[PartySlot] = []
    for spec in slots:
        slot = PartySlot(
            package_id=package_id, starts_at=spec.starts_at, ends_at=spec.ends_at
        )
        db.add(slot)
        created.append(slot)
    db.flush()
    return created


def list_slots(
    db: Session, package_id: uuid.UUID, *, available_only: bool = True,
    now: datetime | None = None,
) -> list[PartySlot]:
    """Public: a package's upcoming slots (available ones by default)."""
    moment = now or datetime.now(UTC)
    stmt = (
        select(PartySlot)
        .where(PartySlot.package_id == package_id, PartySlot.starts_at >= moment)
        .order_by(PartySlot.starts_at)
    )
    if available_only:
        stmt = stmt.where(PartySlot.status == PartySlotStatus.available)
    return list(db.scalars(stmt))


# --- Booking + deposit (Milestone B2, ADR-0007) -----------------------------

def _deposit_pct(db: Session, package: PartyPackage) -> int:
    return package.deposit_pct or config_service.party_deposit_pct(db)


def get_booking(db: Session, booking_id: uuid.UUID) -> PartyBooking | None:
    return db.get(PartyBooking, booking_id)


def book_slot(
    db: Session,
    *,
    slot_id: uuid.UUID,
    guardian_id: uuid.UUID,
    headcount: int,
    gateway: PaymentGateway,
) -> tuple[PartyBooking, PaymentIntentResult]:
    """Reserve a party slot (capacity-1, INV-1) and start the deposit PaymentIntent
    (ADR-0007). The slot row is locked and transitioned available→held under the lock;
    a partial UNIQUE on (slot_id WHERE status<>cancelled) is the DB backstop. The deposit
    saves the card off-session for the T-7d balance (B3). Confirmation is webhook-driven."""
    slot = db.execute(
        select(PartySlot).where(PartySlot.id == slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise SlotNotFound(str(slot_id))
    if slot.status is not PartySlotStatus.available:
        raise SlotUnavailable(str(slot_id))
    package = db.get(PartyPackage, slot.package_id)
    if package is None:
        raise PackageNotFound(str(slot.package_id))
    if not (package.min_headcount <= headcount <= package.max_headcount):
        raise HeadcountOutOfBand(str(headcount))

    total = package.per_head_price_cents * headcount
    deposit = round(total * _deposit_pct(db, package) / 100)
    booking = PartyBooking(
        slot_id=slot.id,
        package_id=package.id,
        guardian_id=guardian_id,
        organisation_id=package.organisation_id,
        headcount=headcount,
        per_head_price_cents=package.per_head_price_cents,
        total_cents=total,
        deposit_cents=deposit,
        balance_cents=total - deposit,
        status=PartyBookingStatus.pending_deposit,
    )
    db.add(booking)
    # The partial UNIQUE (one non-cancelled booking per slot) is the INV-1 DB backstop; the
    # FOR UPDATE above normally 409s first, but if it ever fires, surface a clean 409 (not 500).
    savepoint = db.begin_nested()
    try:
        db.flush()
    except IntegrityError as exc:
        savepoint.rollback()
        raise SlotUnavailable(str(slot_id)) from exc

    payment, intent = payments_service.create_payment(
        db,
        guardian_id=guardian_id,
        amount_cents=deposit,
        application_fee_cents=0,
        fee_gst_cents=0,
        idempotency_key=f"party-deposit-{booking.id}",
        gateway=gateway,
        purpose=PaymentPurpose.party_deposit,
        setup_future_usage="off_session",
    )
    booking.deposit_payment_id = payment.id
    slot.status = PartySlotStatus.held
    db.flush()
    return booking, intent


def _booking_for_payment(db: Session, payment_id: uuid.UUID) -> PartyBooking | None:
    return db.scalar(
        select(PartyBooking).where(PartyBooking.deposit_payment_id == payment_id)
    )


def settle_deposit_succeeded(
    db: Session, *, intent_id: str, gateway: PaymentGateway
) -> None:
    """payment_intent.succeeded for a party deposit: confirm the booking + book the slot.
    Row-locks the payment; idempotent on redelivery (ADR-0005 §3 pattern)."""
    payment = payments_service.get_payment_by_intent(db, intent_id, for_update=True)
    if payment is None or payment.status in (
        PaymentStatus.succeeded,
        PaymentStatus.refunded,
    ):
        return
    booking = _booking_for_payment(db, payment.id)
    if booking is None:
        return
    if booking.status is PartyBookingStatus.cancelled:
        # The slot was released before the (late) deposit landed → refund it (ADR-0010).
        payments_service.refund(db, payment, gateway=gateway)
        return
    payments_service.mark_succeeded(db, payment)
    booking.status = PartyBookingStatus.confirmed
    slot = db.get(PartySlot, booking.slot_id)
    if slot is not None and slot.status is not PartySlotStatus.cancelled:
        slot.status = PartySlotStatus.booked
    db.flush()


def _release(db: Session, booking: PartyBooking) -> None:
    booking.status = PartyBookingStatus.cancelled
    slot = db.get(PartySlot, booking.slot_id)
    if slot is not None and slot.status in (PartySlotStatus.held, PartySlotStatus.booked):
        slot.status = PartySlotStatus.available
    db.flush()


def settle_deposit_canceled(db: Session, *, intent_id: str) -> None:
    """payment_intent.canceled for a party deposit: release the slot, fail the booking."""
    payment = payments_service.get_payment_by_intent(db, intent_id, for_update=True)
    if payment is None or payment.status is not PaymentStatus.pending:
        return
    booking = _booking_for_payment(db, payment.id)
    if booking is not None and booking.status is PartyBookingStatus.pending_deposit:
        _release(db, booking)
    payments_service.mark_failed(db, payment)


def sweep_abandoned_deposits(
    db: Session, *, gateway: PaymentGateway, now: datetime | None = None
) -> int:
    """Terminal outcome for party bookings whose deposit never completed (ADR-0005 §1):
    an unconfirmed deposit PaymentIntent gets no terminal Stripe event, so a booked slot
    would otherwise stay ``held`` forever (INV-1 strand). For each pending party-deposit
    payment older than the checkout window, cancel the PI, release the slot, fail the order.
    ``FOR UPDATE SKIP LOCKED`` + status guards make it idempotent."""
    moment = now or datetime.now(UTC)
    deadline = moment - timedelta(seconds=config_service.checkout_window_seconds(db))
    stale = db.scalars(
        select(Payment)
        .where(
            Payment.purpose == PaymentPurpose.party_deposit,
            Payment.status == PaymentStatus.pending,
            Payment.created_at < deadline,
        )
        .with_for_update(skip_locked=True)
    ).all()
    swept = 0
    for payment in stale:
        booking = _booking_for_payment(db, payment.id)
        if booking is None or booking.status is not PartyBookingStatus.pending_deposit:
            continue
        if payment.stripe_payment_intent_id is not None:
            gateway.cancel_payment_intent(payment.stripe_payment_intent_id)
        _release(db, booking)
        payments_service.mark_failed(db, payment)
        swept += 1
    db.flush()
    return swept
