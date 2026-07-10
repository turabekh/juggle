"""Business logic for the payments module.

All mutations funnel through a module service (no side-door SQL) so the admin
panel and product share one code path (PRD §10.4).

The application-fee rate is a runtime-config lever (PRD §10.1); until the config
module is wired (M7) it is a module constant.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.config.core import service as config_service
from juggle.modules.payments.core.gateway import PaymentGateway
from juggle.modules.payments.core.models import Payment, PaymentStatus


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
