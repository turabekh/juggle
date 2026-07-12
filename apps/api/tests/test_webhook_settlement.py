"""Webhook-driven settlement (F-PAY-3, ADR-0005 §3-§4): payment_intent.succeeded confirms
a firm order (or auto-refunds a lost seat), payment_intent.canceled releases, and
payment_intent.payment_failed is non-terminal. Signatures are real HMAC, never mocked."""

import hashlib
import hmac
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.notifications.core.models import NotificationLog
from juggle.modules.payments.core.models import Payment, PaymentStatus
from juggle.settings import get_settings

_WEBHOOK_SECRET = "whsec_test_f_pay_3"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


@pytest.fixture
def webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", _WEBHOOK_SECRET)


def _post_pi_event(client: TestClient, *, event_id: str, event_type: str, intent_id: str) -> dict:
    payload = {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "data": {"object": {"id": intent_id}},
    }
    body = json.dumps(payload).encode()
    ts = int(time.time())
    signed = f"{ts}.".encode() + body
    sig = hmac.new(_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    headers = {"Stripe-Signature": f"t={ts},v1={sig}"}
    return client.post("/api/v1/booking/stripe/webhook", content=body, headers=headers).json()


def _published_session(client: TestClient, owner: str, *, capacity: int = 1) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues", headers=_auth(owner),
        json={"organisation_id": org_id, "name": "Hall"},
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs", headers=_auth(owner),
        json={"organisation_id": org_id, "title": "Camp", "category": "art"},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions", headers=_auth(owner),
        json={
            "venue_id": venue_id,
            "starts_at": "2026-01-05T01:00:00Z",
            "ends_at": "2026-01-05T07:00:00Z",
            "capacity": capacity,
            "price_cents": 10000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return org_id, session_id


def _checkout(client: TestClient, guardian: str, session_id: str) -> str:
    hold_id = client.post(
        "/api/v1/inventory/holds", headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children", headers=_auth(guardian),
        json={"first_name": "Kid", "date_of_birth": "2018-01-01"},
    ).json()["id"]
    return client.post(
        "/api/v1/booking/checkout", headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()["payment_id"]


def _payment(db: Session, payment_id: str) -> Payment:
    payment = db.scalar(select(Payment).where(Payment.id == uuid.UUID(payment_id)))
    assert payment is not None
    return payment


def _remaining(client: TestClient, session_id: str) -> int:
    return client.get(
        f"/api/v1/inventory/sessions/{session_id}/availability"
    ).json()["seats_remaining"]


def test_payment_intent_succeeded_confirms_and_accrues(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    org_id, session_id = _published_session(client, owner, capacity=1)
    payment_id = _checkout(client, guardian, session_id)
    pi = _payment(db, payment_id).stripe_payment_intent_id
    assert pi is not None

    ack = _post_pi_event(
        client, event_id="evt_ok", event_type="payment_intent.succeeded", intent_id=pi
    )
    assert ack["status"] == "ok"

    assert _payment(db, payment_id).status is PaymentStatus.succeeded
    bookings = client.get("/api/v1/booking/bookings", headers=_auth(guardian)).json()
    assert bookings[0]["status"] == "confirmed"
    assert _remaining(client, session_id) == 0  # seat consumed, still taken
    payouts = client.get(
        "/api/v1/payments/payouts", headers=_auth(owner), params={"organisation_id": org_id}
    ).json()
    assert len(payouts) == 1
    assert payouts[0]["amount_cents"] == 8900  # 10000 − fee − GST (ADR-0002)

    # Redelivery of the same event is a deduped no-op.
    again = _post_pi_event(
        client, event_id="evt_ok", event_type="payment_intent.succeeded", intent_id=pi
    )
    assert again["status"] == "duplicate"


def test_payment_intent_canceled_releases_seat(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    _org, session_id = _published_session(client, owner, capacity=1)
    payment_id = _checkout(client, guardian, session_id)
    pi = _payment(db, payment_id).stripe_payment_intent_id
    assert pi is not None
    assert _remaining(client, session_id) == 0

    ack = _post_pi_event(
        client, event_id="evt_cx", event_type="payment_intent.canceled", intent_id=pi
    )
    assert ack["status"] == "ok"
    assert _payment(db, payment_id).status is PaymentStatus.failed
    assert _remaining(client, session_id) == 1  # seat freed


def test_payment_failed_is_non_terminal(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    _org, session_id = _published_session(client, owner, capacity=1)
    payment_id = _checkout(client, guardian, session_id)
    pi = _payment(db, payment_id).stripe_payment_intent_id
    assert pi is not None

    ack = _post_pi_event(
        client, event_id="evt_f", event_type="payment_intent.payment_failed", intent_id=pi
    )
    assert ack["status"] == "ok"
    # A retry can still succeed on the same PI: the seat stays held and the payment pending.
    assert _payment(db, payment_id).status is PaymentStatus.pending
    assert _remaining(client, session_id) == 0


def test_succeeded_after_session_cancel_auto_refunds(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    _org, session_id = _published_session(client, owner, capacity=1)
    payment_id = _checkout(client, guardian, session_id)
    pi = _payment(db, payment_id).stripe_payment_intent_id
    assert pi is not None

    # Provider cancels the session while the payment is still pending (seat released,
    # payment failed); the PI then succeeds — the seat is gone, so we auto-refund.
    client.post(f"/api/v1/booking/sessions/{session_id}/cancel", headers=_auth(owner))
    ack = _post_pi_event(
        client, event_id="evt_lost", event_type="payment_intent.succeeded", intent_id=pi
    )
    assert ack["status"] == "ok"
    assert _payment(db, payment_id).status is PaymentStatus.refunded
    guardian_id = _payment(db, payment_id).guardian_id
    notes = db.scalars(
        select(NotificationLog).where(
            NotificationLog.user_account_id == guardian_id,
            NotificationLog.kind == "seat_unavailable_refund",
        )
    ).all()
    assert len(notes) == 1


def test_sync_confirm_blocked_when_live_stripe(client: TestClient, db: Session) -> None:
    """With the real Stripe gateway active, the synchronous confirm endpoint is refused —
    confirmation must come from the verified webhook, not a client call (ADR-0005 §5)."""
    from juggle.main import app
    from juggle.modules.payments.core.gateway import StripeGateway, get_payment_gateway

    owner, guardian = _signup(client), _signup(client)
    _org, session_id = _published_session(client, owner, capacity=1)
    payment_id = _checkout(client, guardian, session_id)  # created with the fake gateway

    app.dependency_overrides[get_payment_gateway] = lambda: StripeGateway("sk_test_dummy")
    try:
        resp = client.post(
            f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian)
        )
    finally:
        app.dependency_overrides.pop(get_payment_gateway, None)
    assert resp.status_code == 409
    assert _payment(db, payment_id).status is PaymentStatus.pending  # not confirmed


def test_webhook_for_unknown_intent_is_a_noop(
    client: TestClient, webhook_secret: None
) -> None:
    ack = _post_pi_event(
        client, event_id="evt_unknown", event_type="payment_intent.succeeded",
        intent_id="pi_does_not_exist",
    )
    assert ack["status"] == "ok"  # recorded + ignored, no error
