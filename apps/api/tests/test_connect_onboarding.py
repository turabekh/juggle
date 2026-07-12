"""Connect Express onboarding + the account.updated webhook + payout gating (F-PAY-1).

Webhook signatures are NEVER mocked: tests compute a real Stripe-scheme HMAC over the
raw body with a test endpoint secret, so ``stripe.Webhook.construct_event`` genuinely
verifies (CLAUDE §5).
"""

import hashlib
import hmac
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from juggle.modules.org.core import service as org_service
from juggle.settings import get_settings

_WEBHOOK_SECRET = "whsec_test_f_pay_1"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _make_org(client: TestClient, owner: str) -> str:
    return client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]


def _signed_event(payload: dict[str, object]) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    ts = int(time.time())
    signed = f"{ts}.".encode() + body
    sig = hmac.new(_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={ts},v1={sig}"}


@pytest.fixture
def webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", _WEBHOOK_SECRET)


def test_payment_config_reports_dev_mode_without_stripe_keys(client: TestClient) -> None:
    # No JUGGLE_STRIPE_SECRET_KEY in the test env → the client uses the dev sync-confirm flow.
    body = client.get("/api/v1/payments/config").json()
    assert body == {"live": False, "publishable_key": None}


def test_onboarding_creates_account_and_link(client: TestClient) -> None:
    owner = _signup(client)
    org_id = _make_org(client, owner)

    resp = client.post(
        "/api/v1/payments/connect/onboard", headers=_auth(owner),
        json={"organisation_id": org_id},
    )
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://")

    # A freshly created account is onboarded (has an account id) but not yet enabled.
    status = client.get(
        "/api/v1/payments/connect/status", headers=_auth(owner),
        params={"organisation_id": org_id},
    ).json()
    assert status == {"onboarded": True, "charges_enabled": False, "payouts_enabled": False}


def test_refresh_enables_capabilities(client: TestClient) -> None:
    owner = _signup(client)
    org_id = _make_org(client, owner)
    client.post(
        "/api/v1/payments/connect/onboard", headers=_auth(owner),
        json={"organisation_id": org_id},
    )
    refreshed = client.post(
        "/api/v1/payments/connect/refresh", headers=_auth(owner),
        json={"organisation_id": org_id},
    ).json()
    assert refreshed == {"onboarded": True, "charges_enabled": True, "payouts_enabled": True}


def test_onboarding_requires_membership(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    org_id = _make_org(client, owner)
    resp = client.post(
        "/api/v1/payments/connect/onboard", headers=_auth(outsider),
        json={"organisation_id": org_id},
    )
    assert resp.status_code == 403


def test_account_updated_webhook_sets_flags(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner = _signup(client)
    org_id = _make_org(client, owner)
    org_service.set_stripe_account(db, uuid.UUID(org_id), "acct_hook_1")
    db.flush()

    body, headers = _signed_event(
        {
            "id": "evt_1",
            "object": "event",
            "type": "account.updated",
            "data": {"object": {"id": "acct_hook_1", "charges_enabled": True,
                                "payouts_enabled": True}},
        }
    )
    resp = client.post("/api/v1/booking/stripe/webhook", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    status = client.get(
        "/api/v1/payments/connect/status", headers=_auth(owner),
        params={"organisation_id": org_id},
    ).json()
    assert status["charges_enabled"] is True
    assert status["payouts_enabled"] is True


def test_webhook_is_idempotent(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner = _signup(client)
    org_id = _make_org(client, owner)
    org_service.set_stripe_account(db, uuid.UUID(org_id), "acct_hook_2")
    db.flush()

    body, headers = _signed_event(
        {
            "id": "evt_dup",
            "object": "event",
            "type": "account.updated",
            "data": {"object": {"id": "acct_hook_2", "charges_enabled": True,
                                "payouts_enabled": True}},
        }
    )
    first = client.post("/api/v1/booking/stripe/webhook", content=body, headers=headers)
    second = client.post("/api/v1/booking/stripe/webhook", content=body, headers=headers)
    assert first.json()["status"] == "ok"
    assert second.json()["status"] == "duplicate"
    # Flags remain correctly set after the redelivery (no double-apply, no rollback).
    status = client.get(
        "/api/v1/payments/connect/status", headers=_auth(owner),
        params={"organisation_id": org_id},
    ).json()
    assert status["payouts_enabled"] is True


def test_webhook_rejects_bad_signature(client: TestClient, webhook_secret: None) -> None:
    body = json.dumps({"id": "evt_x", "type": "account.updated", "data": {"object": {}}}).encode()
    resp = client.post(
        "/api/v1/booking/stripe/webhook", content=body,
        headers={"Stripe-Signature": "t=1,v1=deadbeef"},
    )
    assert resp.status_code == 400


def test_payout_gated_on_payouts_enabled(
    client: TestClient, make_admin, db: Session  # noqa: ANN001
) -> None:
    owner, guardian, admin = _signup(client), _signup(client), make_admin()
    org_id = _make_org(client, owner)
    # Onboard but do NOT enable capabilities (no refresh): payouts must not release.
    client.post(
        "/api/v1/payments/connect/onboard", headers=_auth(owner),
        json={"organisation_id": org_id},
    )
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
        json={"venue_id": venue_id, "starts_at": "2026-01-05T01:00:00Z",
              "ends_at": "2026-01-05T07:00:00Z", "capacity": 5, "price_cents": 10000,
              "age_min": 4, "age_max": 12},
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))

    hold_id = client.post(
        "/api/v1/inventory/holds", headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children", headers=_auth(guardian),
        json={"first_name": "Kid", "date_of_birth": "2018-01-01"},
    ).json()["id"]
    order = client.post(
        "/api/v1/booking/checkout", headers=_auth(guardian),
        json={"idempotency_key": f"key-{uuid.uuid4().hex}",
              "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}]},
    ).json()
    client.post(
        f"/api/v1/booking/payments/{order['payment_id']}/confirm", headers=_auth(guardian)
    )

    # Not payouts_enabled → the due payout is skipped, left scheduled.
    run = client.post("/api/v1/admin/payouts/run", headers=_auth(admin))
    assert run.json()["released"] == 0

    # Enable, then it releases.
    client.post(
        "/api/v1/payments/connect/refresh", headers=_auth(owner),
        json={"organisation_id": org_id},
    )
    run = client.post("/api/v1/admin/payouts/run", headers=_auth(admin))
    assert run.json()["released"] == 1
