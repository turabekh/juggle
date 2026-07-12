"""Business logic for the payments module.

All mutations funnel through a module service (no side-door SQL) so the admin
panel and product share one code path (PRD §10.4).

The application-fee rate is a runtime-config lever (PRD §10.1); until the config
module is wired (M7) it is a module constant.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from juggle.modules.identity.core import service as identity_service
from juggle.modules.org.core import service as org_service
from juggle.modules.payments.core.gateway import (
    AccountLinkResult,
    PaymentGateway,
    PaymentIntentResult,
)
from juggle.modules.payments.core.models import (
    Payment,
    PaymentStatus,
    Payout,
    PayoutStatus,
    StripeEvent,
)


class NotOrgMember(Exception):
    """Caller is not a member of the organisation."""


class OrgNotFound(Exception):
    """No such organisation."""


class WebhookVerificationError(Exception):
    """The Stripe webhook signature did not verify."""


class PayoutNotFound(Exception):
    """No such payout."""


def application_fee_cents(amount_cents: int, fee_rate: float) -> int:
    # The 10% commission, ex-GST — platform revenue (ADR-0002).
    return round(amount_cents * fee_rate)


def fee_gst_cents(fee_cents: int, gst_rate: float) -> int:
    # GST on the commission — the platform remits this to the ATO (ADR-0002, INV-6).
    return round(fee_cents * gst_rate)


def take_rate(line_cents: int, fee_rate: float, gst_rate: float) -> tuple[int, int, int]:
    """Split one GST-inclusive line into (fee, gst, net) with per-session rounding
    (ADR-0002). ``net`` is the derived remainder so fee+gst+net == line_cents exactly."""
    fee = application_fee_cents(line_cents, fee_rate)
    gst = fee_gst_cents(fee, gst_rate)
    return fee, gst, line_cents - fee - gst


def create_payment(
    db: Session,
    *,
    guardian_id: uuid.UUID,
    amount_cents: int,
    application_fee_cents: int,
    fee_gst_cents: int,
    idempotency_key: str,
    gateway: PaymentGateway,
    currency: str = "aud",
) -> tuple[Payment, PaymentIntentResult]:
    """Create the Stripe PaymentIntent (separate charge — no application_fee/destination,
    ADR-0001/0005) and the local Payment row. The caller passes the per-session-summed
    fee + GST so rounding stays per-session (ADR-0002). Returns the payment and the intent
    so the caller can hand the client_secret to the Payment Element."""
    intent = gateway.create_payment_intent(
        amount_cents=amount_cents,
        application_fee_cents=application_fee_cents,
        currency=currency,
        idempotency_key=idempotency_key,
    )
    payment = Payment(
        guardian_id=guardian_id,
        stripe_payment_intent_id=intent.id,
        idempotency_key=idempotency_key,
        amount_cents=amount_cents,
        application_fee_cents=application_fee_cents,
        fee_gst_cents=fee_gst_cents,
        currency=currency,
        status=PaymentStatus.pending,
    )
    db.add(payment)
    db.flush()
    return payment, intent


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


def get_payment_for_update(db: Session, payment_id: uuid.UUID) -> Payment | None:
    """Row-locked read for settlement transitions (confirm / cancel / sweep), so two
    paths can't act on a stale ``pending`` read of the same payment (ADR-0005 §3)."""
    return db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())


def mark_succeeded(db: Session, payment: Payment) -> Payment:
    """Record an already-succeeded charge. The gateway is NOT called here — the client
    confirms the PaymentIntent and the webhook is the source of truth (ADR-0005 §5)."""
    if payment.status is PaymentStatus.succeeded:
        return payment
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


# --- Connect Express onboarding + webhooks (F-PAY-1) ------------------------

def start_onboarding(
    db: Session,
    *,
    organisation_id: uuid.UUID,
    actor_id: uuid.UUID,
    gateway: PaymentGateway,
    refresh_url: str,
    return_url: str,
) -> AccountLinkResult:
    """Create (or reuse) the org's Stripe Express account and return a hosted
    onboarding link. Member-gated. All Stripe calls stay in this module (INV-2)."""
    org = org_service.get_organisation(db, organisation_id)
    if org is None:
        raise OrgNotFound(str(organisation_id))
    if org_service.get_member(db, organisation_id, actor_id) is None:
        raise NotOrgMember(str(organisation_id))
    if org.stripe_account_id is None:
        actor = identity_service.get_user(db, actor_id)
        account = gateway.create_connect_account(
            email=actor.email if actor is not None else None, business_name=org.name
        )
        org_service.set_stripe_account(db, organisation_id, account.id)
        org_service.set_connect_flags(
            db,
            organisation_id,
            charges_enabled=account.charges_enabled,
            payouts_enabled=account.payouts_enabled,
        )
        account_id = account.id
    else:
        account_id = org.stripe_account_id
    return gateway.create_account_link(
        account_id=account_id, refresh_url=refresh_url, return_url=return_url
    )


def connect_status(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> dict[str, bool]:
    """The org's Stripe onboarding/capability state (member-gated)."""
    org = org_service.get_organisation(db, organisation_id)
    if org is None:
        raise OrgNotFound(str(organisation_id))
    if org_service.get_member(db, organisation_id, actor_id) is None:
        raise NotOrgMember(str(organisation_id))
    return {
        "onboarded": org.stripe_account_id is not None,
        "charges_enabled": org.charges_enabled,
        "payouts_enabled": org.payouts_enabled,
    }


def refresh_account_status(
    db: Session, *, organisation_id: uuid.UUID, gateway: PaymentGateway
) -> dict[str, bool]:
    """Pull the org's current capability flags from Stripe and mirror them locally.
    A synchronous fallback for the ``account.updated`` webhook (e.g. on onboarding
    return, or admin-triggered)."""
    org = org_service.get_organisation(db, organisation_id)
    if org is None:
        raise OrgNotFound(str(organisation_id))
    if org.stripe_account_id is None:
        return {"onboarded": False, "charges_enabled": False, "payouts_enabled": False}
    account = gateway.retrieve_account(org.stripe_account_id)
    org_service.set_connect_flags(
        db,
        organisation_id,
        charges_enabled=account.charges_enabled,
        payouts_enabled=account.payouts_enabled,
    )
    return {
        "onboarded": True,
        "charges_enabled": account.charges_enabled,
        "payouts_enabled": account.payouts_enabled,
    }


@dataclass(frozen=True)
class WebhookEvent:
    """A verified Stripe event, reduced to a Stripe-free shape so higher modules can
    dispatch on it without importing ``stripe`` (keeps all Stripe types inside payments)."""

    id: str
    type: str
    data_object: dict[str, Any]


def verify_event(payload: bytes, sig_header: str, secret: str) -> WebhookEvent:
    """Verify a Stripe webhook signature on the RAW body (never trust an unverified
    payload) and return the event as a Stripe-free ``WebhookEvent`` (INV-2). The
    signature is checked via Stripe; fields are then read from the raw JSON (plain dicts,
    avoiding StripeObject's attribute quirks)."""
    try:
        stripe.Webhook.construct_event(  # type: ignore[no-untyped-call]
            payload, sig_header, secret
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise WebhookVerificationError(str(exc)) from exc
    data = json.loads(payload)
    return WebhookEvent(
        id=str(data["id"]),
        type=str(data["type"]),
        data_object=dict(data["data"]["object"]),
    )


def record_event(db: Session, event_id: str, event_type: str) -> bool:
    """Insert the event id into the idempotency ledger. Returns False if it was
    already recorded (a Stripe redelivery — at-least-once), so the caller no-ops.

    The insert runs inside a SAVEPOINT so a duplicate-key collision rolls back only
    this insert, not the surrounding transaction (INV-2)."""
    savepoint = db.begin_nested()
    db.add(StripeEvent(event_id=event_id, event_type=event_type))
    try:
        db.flush()
    except IntegrityError:
        savepoint.rollback()
        return False
    return True


def apply_account_updated(
    db: Session, *, account_id: str, charges_enabled: bool, payouts_enabled: bool
) -> None:
    """Mirror a Connect account's capability flags locally (from the account.updated
    webhook, dispatched by the booking-hosted Stripe sink)."""
    org = org_service.get_org_by_stripe_account(db, account_id)
    if org is None:
        return
    org_service.set_connect_flags(
        db, org.id, charges_enabled=charges_enabled, payouts_enabled=payouts_enabled
    )


def get_payment_by_intent(
    db: Session, intent_id: str, *, for_update: bool = False
) -> Payment | None:
    stmt = select(Payment).where(Payment.stripe_payment_intent_id == intent_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


# --- Payouts (PRD §8.4) -----------------------------------------------------

def provider_net_cents(gross_cents: int, fee_rate: float, gst_rate: float) -> int:
    """What the provider earns after the platform commission and its GST (ADR-0002)."""
    _fee, _gst, net = take_rate(gross_cents, fee_rate, gst_rate)
    return net


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
    released = 0
    for payout in due:
        org = org_service.get_organisation(db, payout.organisation_id)
        # Gate on Connect readiness (F-PAY-1): a provider who is not payouts_enabled or
        # has no connected account is skipped, leaving the payout scheduled for a later
        # run — never transferred to a dead-end destination.
        if org is None or not org.payouts_enabled or org.stripe_account_id is None:
            continue
        result = gateway.transfer(
            destination=org.stripe_account_id, amount_cents=payout.amount_cents
        )
        payout.stripe_transfer_id = result.id
        payout.status = PayoutStatus.paid
        total += payout.amount_cents
        released += 1
    db.flush()
    return released, total
