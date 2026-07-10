"""Business logic for the payments module.

All mutations funnel through a module service (no side-door SQL) so the admin
panel and product share one code path (PRD §10.4).

The application-fee rate is a runtime-config lever (PRD §10.1); until the config
module is wired (M7) it is a module constant.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.config.core import service as config_service
from juggle.modules.org.core import service as org_service
from juggle.modules.payments.core.gateway import PaymentGateway
from juggle.modules.payments.core.models import Payment, PaymentStatus, Payout, PayoutStatus


class NotOrgMember(Exception):
    """Caller is not a member of the organisation."""


class PayoutNotFound(Exception):
    """No such payout."""


def application_fee_cents(amount_cents: int, fee_rate: float) -> int:
    # GST on the fee is a separate invoicing line (D-02); this is commission only.
    return round(amount_cents * fee_rate)


def create_payment(
    db: Session,
    *,
    guardian_id: uuid.UUID,
    amount_cents: int,
    idempotency_key: str,
    gateway: PaymentGateway,
    currency: str = "aud",
) -> Payment:
    fee = application_fee_cents(amount_cents, config_service.platform_fee_rate(db))
    intent = gateway.create_payment_intent(
        amount_cents=amount_cents,
        application_fee_cents=fee,
        currency=currency,
        idempotency_key=idempotency_key,
    )
    payment = Payment(
        guardian_id=guardian_id,
        stripe_payment_intent_id=intent.id,
        idempotency_key=idempotency_key,
        amount_cents=amount_cents,
        application_fee_cents=fee,
        currency=currency,
        status=PaymentStatus.pending,
    )
    db.add(payment)
    db.flush()
    return payment


def find_by_idempotency_key(
    db: Session, *, guardian_id: uuid.UUID, idempotency_key: str
) -> Payment | None:
    return db.scalar(
        select(Payment).where(
            Payment.guardian_id == guardian_id,
            Payment.idempotency_key == idempotency_key,
        )
    )


def get_payment(db: Session, payment_id: uuid.UUID) -> Payment | None:
    return db.get(Payment, payment_id)


def mark_succeeded(db: Session, payment: Payment, *, gateway: PaymentGateway) -> Payment:
    if payment.status is PaymentStatus.succeeded:
        return payment
    if payment.stripe_payment_intent_id is not None:
        gateway.confirm(payment.stripe_payment_intent_id)
    payment.status = PaymentStatus.succeeded
    db.flush()
    return payment


def mark_failed(db: Session, payment: Payment) -> Payment:
    payment.status = PaymentStatus.failed
    db.flush()
    return payment


def refund(db: Session, payment: Payment, *, gateway: PaymentGateway) -> Payment:
    """Full refund via the gateway; idempotent once already refunded."""
    if payment.status is PaymentStatus.refunded:
        return payment
    if payment.stripe_payment_intent_id is not None:
        gateway.refund(payment.stripe_payment_intent_id, payment.amount_cents)
    payment.status = PaymentStatus.refunded
    db.flush()
    return payment


# --- Payouts (PRD §8.4) -----------------------------------------------------

def provider_net_cents(gross_cents: int, fee_rate: float) -> int:
    """What the provider earns after the platform commission."""
    return gross_cents - application_fee_cents(gross_cents, fee_rate)


def accrue_payout(
    db: Session,
    *,
    organisation_id: uuid.UUID,
    session_id: uuid.UUID,
    net_cents: int,
    scheduled_for: datetime,
) -> Payout:
    """Add a provider's net earnings for a session to its (single) scheduled
    payout, creating it if needed. Paid on/after ``scheduled_for``."""
    payout = db.scalar(
        select(Payout).where(
            Payout.session_id == session_id, Payout.status == PayoutStatus.scheduled
        )
    )
    if payout is None:
        payout = Payout(
            organisation_id=organisation_id,
            session_id=session_id,
            amount_cents=0,
            status=PayoutStatus.scheduled,
            scheduled_for=scheduled_for,
        )
        db.add(payout)
        db.flush()
    payout.amount_cents += net_cents
    db.flush()
    return payout


def list_org_payouts(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> list[Payout]:
    if org_service.get_member(db, organisation_id, actor_id) is None:
        raise NotOrgMember(str(organisation_id))
    return list(
        db.scalars(
            select(Payout)
            .where(Payout.organisation_id == organisation_id)
            .order_by(Payout.scheduled_for)
        )
    )


def list_payouts_by_status(db: Session, status: PayoutStatus) -> list[Payout]:
    return list(
        db.scalars(select(Payout).where(Payout.status == status).order_by(Payout.scheduled_for))
    )


def set_payout_status(
    db: Session, payout_id: uuid.UUID, status: PayoutStatus
) -> Payout | None:
    payout = db.get(Payout, payout_id)
    if payout is None:
        return None
    payout.status = status
    db.flush()
    return payout


def release_due_payouts(
    db: Session, *, gateway: PaymentGateway, now: datetime | None = None
) -> tuple[int, int]:
    """Pay out every scheduled payout whose time has come. Returns (count, total)."""
    moment = now or datetime.now(UTC)
    due = db.scalars(
        select(Payout).where(
            Payout.status == PayoutStatus.scheduled,
            Payout.scheduled_for <= moment,
        )
    ).all()
    total = 0
    for payout in due:
        org = org_service.get_organisation(db, payout.organisation_id)
        destination = org.stripe_account_id if org is not None else None
        result = gateway.transfer(destination=destination, amount_cents=payout.amount_cents)
        payout.stripe_transfer_id = result.id
        payout.status = PayoutStatus.paid
        total += payout.amount_cents
    db.flush()
    return len(due), total
