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
from juggle.modules.events.core import service as events_service
from juggle.modules.identity.core import service as identity_service
from juggle.modules.notifications.core import service as notifications_service
from juggle.modules.notifications.core.gateway import EmailGateway
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


class NotBookingParty(Exception):
    """Actor is not the guardian who booked this party."""


class NotAuthorisedToCancel(Exception):
    """Actor is neither the booking's guardian nor a member of its provider org."""


class BookingNotConfirmed(Exception):
    """The booking is not in a confirmed state."""


class BalanceAlreadyCharged(Exception):
    """The balance has been captured — adjust via support, not self-serve (B4 scope)."""


class AdjustmentClosed(Exception):
    """Past the T-72h guest-count adjustment cutoff."""


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


# --- Balance auto-charge (Milestone B3, ADR-0008) ---------------------------

def _accrue_party_payout(db: Session, booking: PartyBooking) -> None:
    """Accrue the provider's net on the full party total once the balance captures
    (take-rate per ADR-0002), due after the party runs (ADR-0004). Stores payout_id so a
    later refund claws it back (ADR-0010 / F-PAY-5)."""
    fee_rate = config_service.platform_fee_rate(db)
    gst_rate = config_service.gst_rate(db)
    net = payments_service.provider_net_cents(booking.total_cents, fee_rate, gst_rate)
    slot = db.get(PartySlot, booking.slot_id)
    party_start = slot.starts_at if slot is not None else datetime.now(UTC)
    payout = payments_service.accrue_party_payout(
        db,
        organisation_id=booking.organisation_id,
        net_cents=net,
        scheduled_for=party_start + timedelta(days=config_service.payout_delay_days(db)),
    )
    booking.payout_id = payout.id


def _notify_host(
    db: Session, booking: PartyBooking, *, email_gateway: EmailGateway, cancelled: bool
) -> None:
    guardian = identity_service.get_user(db, booking.guardian_id)
    if guardian is None:
        return
    package = db.get(PartyPackage, booking.package_id)
    title = package.name if package is not None else "your party"
    if cancelled:
        notifications_service.notify_party_cancelled(
            db, user_id=guardian.id, to_email=guardian.email, party_title=title,
            gateway=email_gateway,
        )
    else:
        notifications_service.notify_party_payment_action_needed(
            db, user_id=guardian.id, to_email=guardian.email, party_title=title,
            balance_cents=booking.balance_cents, gateway=email_gateway,
        )


def _attempt_balance(
    db: Session,
    booking: PartyBooking,
    *,
    gateway: PaymentGateway,
    email_gateway: EmailGateway,
    now: datetime,
) -> bool:
    """One off-session balance charge attempt. Records the payment + accrues the payout only
    on success; a decline just increments the attempt counter for the next tick."""
    booking.balance_attempts += 1
    booking.last_balance_attempt_at = now
    deposit = (
        db.get(Payment, booking.deposit_payment_id)
        if booking.deposit_payment_id is not None
        else None
    )
    if deposit is None or deposit.stripe_payment_intent_id is None:
        db.flush()
        return False
    # STABLE idempotency key (ADR-0008): retries are ≥ retry-interval (48h) apart, well beyond
    # Stripe's 24h idempotency window, so each real retry is fresh; but a same-tick redelivery
    # (or an ambiguous success whose response was lost) replays the ONE charge — no double-charge.
    key = f"party-balance-{booking.id}"
    result = gateway.charge_saved_card(
        deposit_intent_id=deposit.stripe_payment_intent_id,
        amount_cents=booking.balance_cents,
        currency=deposit.currency,
        idempotency_key=key,
    )
    if result.status != "succeeded":
        _notify_host(db, booking, email_gateway=email_gateway, cancelled=False)
        db.flush()
        return False
    payment = payments_service.record_payment(
        db,
        guardian_id=booking.guardian_id,
        amount_cents=booking.balance_cents,
        stripe_payment_intent_id=result.id,
        purpose=PaymentPurpose.party_balance,
        status=PaymentStatus.succeeded,
        idempotency_key=key,
    )
    booking.balance_payment_id = payment.id
    booking.balance_captured = True
    _accrue_party_payout(db, booking)
    db.flush()
    return True


def _auto_cancel_unpaid(
    db: Session, booking: PartyBooking, *, gateway: PaymentGateway, email_gateway: EmailGateway
) -> None:
    """Balance unpaid by the cutoff (ADR-0008): refund the deposit (ADR-0010 — a card-glitch
    is not the parent's forfeit), release the slot, cancel the booking, notify the host."""
    if booking.deposit_payment_id is not None:
        deposit = db.get(Payment, booking.deposit_payment_id)
        # Refund unless already fully refunded (refund() is idempotent + handles partials).
        if deposit is not None and deposit.status is not PaymentStatus.refunded:
            payments_service.refund(db, deposit, gateway=gateway)
    _notify_host(db, booking, email_gateway=email_gateway, cancelled=True)
    _release(db, booking)
    events_service.record(
        db, event_type="party_balance_unpaid_cancelled",
        props={"party_booking_id": str(booking.id)},
    )


def process_party_balances(
    db: Session,
    *,
    gateway: PaymentGateway,
    email_gateway: EmailGateway,
    now: datetime | None = None,
) -> int:
    """Scheduler tick (ADR-0008): from T-<offset>d charge each confirmed party's balance
    off-session; retry no more often than the interval, up to max attempts; at T-<cutoff>h
    (or attempts exhausted) auto-cancel + refund the deposit. Idempotent per tick."""
    moment = now or datetime.now(UTC)
    offset_days = config_service.party_balance_offset_days(db)
    cutoff_hours = config_service.party_balance_cutoff_hours(db)
    interval_hours = config_service.party_balance_retry_interval_hours(db)
    max_attempts = config_service.party_balance_max_attempts(db)
    # Guard the config footgun: the charge window must open at or before the cutoff, else a
    # party would auto-cancel un-attempted. Widen the window to always cover the cutoff.
    offset_days = max(offset_days, -(-cutoff_hours // 24))

    # FOR UPDATE SKIP LOCKED so two overlapping ticks never double-process a booking (matches
    # the sibling sweeps); a locked booking is picked up next tick.
    bookings = db.scalars(
        select(PartyBooking)
        .where(
            PartyBooking.status == PartyBookingStatus.confirmed,
            PartyBooking.balance_captured.is_(False),
            PartyBooking.balance_cents > 0,
        )
        .with_for_update(skip_locked=True)
    ).all()
    processed = 0
    for booking in bookings:
        # Isolate each booking in a savepoint so one unexpected error can't wedge the tick.
        savepoint = db.begin_nested()
        try:
            if _process_one_balance(
                db, booking, gateway=gateway, email_gateway=email_gateway, moment=moment,
                offset_days=offset_days, cutoff_hours=cutoff_hours,
                interval_hours=interval_hours, max_attempts=max_attempts,
            ):
                processed += 1
            savepoint.commit()
        except Exception:  # noqa: BLE001 — one bad booking must not abort the whole tick
            savepoint.rollback()
    db.flush()
    return processed


def _process_one_balance(
    db: Session,
    booking: PartyBooking,
    *,
    gateway: PaymentGateway,
    email_gateway: EmailGateway,
    moment: datetime,
    offset_days: int,
    cutoff_hours: int,
    interval_hours: int,
    max_attempts: int,
) -> bool:
    slot = db.get(PartySlot, booking.slot_id)
    if slot is None:
        return False
    party_start = slot.starts_at
    if moment < party_start - timedelta(days=offset_days):
        return False  # too early — balance window not open
    if moment >= party_start - timedelta(hours=cutoff_hours) or (
        booking.balance_attempts >= max_attempts
    ):
        _auto_cancel_unpaid(db, booking, gateway=gateway, email_gateway=email_gateway)
        return True
    last = booking.last_balance_attempt_at
    if last is not None and (moment - last) < timedelta(hours=interval_hours):
        return False  # respect the retry interval
    _attempt_balance(db, booking, gateway=gateway, email_gateway=email_gateway, now=moment)
    return True


# --- Adjustment + cancellation (Milestone B4, ADR-0008 cutoff / ADR-0010) ----

def _lock_booking(db: Session, booking_id: uuid.UUID) -> PartyBooking | None:
    return db.execute(
        select(PartyBooking).where(PartyBooking.id == booking_id).with_for_update()
    ).scalar_one_or_none()


def adjust_headcount(
    db: Session,
    *,
    booking_id: uuid.UUID,
    actor_id: uuid.UUID,
    new_headcount: int,
    gateway: PaymentGateway,
    now: datetime | None = None,
) -> PartyBooking:
    """Change the guest count until the T-72h cutoff (ADR-0008), before the balance is
    captured. Recomputes the total; refunds any now-excess deposit; the later balance charge
    collects the rest. (After-capture adjustments are support-only in B4.)"""
    moment = now or datetime.now(UTC)
    booking = _lock_booking(db, booking_id)
    if booking is None:
        raise PartyBookingNotFound(str(booking_id))
    if booking.guardian_id != actor_id:
        raise NotBookingParty(str(booking_id))
    if booking.status is not PartyBookingStatus.confirmed:
        raise BookingNotConfirmed(str(booking_id))
    if booking.balance_captured:
        raise BalanceAlreadyCharged(str(booking_id))
    package = db.get(PartyPackage, booking.package_id)
    if package is None:
        raise PackageNotFound(str(booking.package_id))
    if not (package.min_headcount <= new_headcount <= package.max_headcount):
        raise HeadcountOutOfBand(str(new_headcount))
    slot = db.get(PartySlot, booking.slot_id)
    cutoff_hours = config_service.party_balance_cutoff_hours(db)
    # Fail closed: a confirmed booking must have a slot, and it must be before the cutoff.
    if slot is None or moment >= slot.starts_at - timedelta(hours=cutoff_hours):
        raise AdjustmentClosed(str(booking_id))

    new_total = package.per_head_price_cents * new_headcount
    if new_total < booking.deposit_cents:
        if booking.deposit_payment_id is not None:
            deposit = db.get(Payment, booking.deposit_payment_id)
            if deposit is not None:
                payments_service.refund(
                    db, deposit, gateway=gateway, amount_cents=booking.deposit_cents - new_total
                )
        booking.deposit_cents = new_total  # clamp regardless of payment existence
    booking.headcount = new_headcount
    booking.total_cents = new_total
    booking.balance_cents = new_total - booking.deposit_cents
    db.flush()
    return booking


def cancel_booking(
    db: Session,
    *,
    booking_id: uuid.UUID,
    actor_id: uuid.UUID,
    gateway: PaymentGateway,
    email_gateway: EmailGateway,
    now: datetime | None = None,
) -> PartyBooking:
    """Cancel a party (ADR-0010). Provider ⇒ 100% refund incl. deposit + full payout clawback.
    Parent ⇒ keeps at most the deposit (refund the balance if captured) + partial clawback.
    Releases the slot; idempotent; clawback targets booking.payout_id."""
    booking = _lock_booking(db, booking_id)
    if booking is None:
        raise PartyBookingNotFound(str(booking_id))
    if booking.status is PartyBookingStatus.cancelled:
        return booking
    # The booking's own guardian cancels as the PARENT (deposit-forfeit floor), even if they
    # happen to be a member of the provider org; only a non-guardian member cancels as provider.
    is_parent = booking.guardian_id == actor_id
    provider_cancel = (not is_parent) and (
        org_service.get_member(db, booking.organisation_id, actor_id) is not None
    )
    if not (is_parent or provider_cancel):
        raise NotAuthorisedToCancel(str(booking_id))

    deposit = (
        db.get(Payment, booking.deposit_payment_id)
        if booking.deposit_payment_id is not None else None
    )
    balance = (
        db.get(Payment, booking.balance_payment_id)
        if booking.balance_payment_id is not None else None
    )
    # Provider refunds the deposit (only if it was actually captured); the parent keeps it.
    if provider_cancel and deposit is not None and deposit.status is PaymentStatus.succeeded:
        payments_service.refund(db, deposit, gateway=gateway)
    # Both refund the balance if it was captured.
    if booking.balance_captured and balance is not None and (
        balance.status is PaymentStatus.succeeded
    ):
        payments_service.refund(db, balance, gateway=gateway)

    # Reduce the provider payout to their net on the RETAINED amount (0 for a provider cancel,
    # the kept deposit for a parent cancel). Computed by subtraction so it reconciles exactly
    # to the accrued net(total) with no rounding leak (ADR-0002 net is non-additive).
    if booking.payout_id is not None:
        fee_rate = config_service.platform_fee_rate(db)
        gst_rate = config_service.gst_rate(db)
        retained_cents = 0 if provider_cancel else booking.deposit_cents
        clawback = payments_service.provider_net_cents(
            booking.total_cents, fee_rate, gst_rate
        ) - payments_service.provider_net_cents(retained_cents, fee_rate, gst_rate)
        if clawback > 0:
            payments_service.adjust_payout_for_refund(
                db,
                payout_id=booking.payout_id,
                net_cents=clawback,
                gateway=gateway,
                idempotency_key=f"party-cancel-{booking.id}",
            )
    _notify_host(db, booking, email_gateway=email_gateway, cancelled=True)
    _release(db, booking)
    events_service.record(
        db, event_type="party_cancelled",
        props={
            "party_booking_id": str(booking.id),
            "by": "provider" if provider_cancel else "parent",
        },
    )
    return booking
