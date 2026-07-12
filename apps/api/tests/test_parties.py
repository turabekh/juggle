"""Parties supply side (Milestone B1, ADR-0006/PRD §9): a provider's party packages +
capacity-1 slots. Member-gated CRUD; public reads. No money yet (B2–B4)."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from juggle.modules.notifications.core.gateway import FakeEmailGateway
from juggle.modules.parties.core import service as parties_service
from juggle.modules.parties.core.models import PartyBooking, PartyBookingStatus
from juggle.modules.payments.core.gateway import FakeGateway, PaymentIntentResult
from juggle.modules.payments.core.models import Payment
from juggle.settings import get_settings

_WEBHOOK_SECRET = "whsec_test_parties"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", _WEBHOOK_SECRET)


def _post_pi_event(client: TestClient, *, event_id: str, event_type: str, intent_id: str) -> dict:
    payload = {
        "id": event_id, "object": "event", "type": event_type,
        "data": {"object": {"id": intent_id}},
    }
    body = json.dumps(payload).encode()
    ts = int(time.time())
    sig = hmac.new(_WEBHOOK_SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/booking/stripe/webhook", content=body,
        headers={"Stripe-Signature": f"t={ts},v1={sig}"},
    ).json()


def _deposit_pi(db: Session, booking_id: str) -> str:
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None and booking.deposit_payment_id is not None
    payment = db.get(Payment, booking.deposit_payment_id)
    assert payment is not None and payment.stripe_payment_intent_id is not None
    return payment.stripe_payment_intent_id


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_with_venue(client: TestClient, owner: str) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues", headers=_auth(owner),
        json={"organisation_id": org_id, "name": "Party Hall"},
    ).json()["id"]
    return org_id, venue_id


def _package_body(venue_id: str, **over: object) -> dict[str, object]:
    return {
        "venue_id": venue_id,
        "name": "Superhero Party",
        "per_head_price_cents": 3500,
        "min_headcount": 8,
        "max_headcount": 20,
        "outdoor": False,
        **over,
    }


def test_create_and_list_package(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)

    resp = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id, deposit_pct=30),
    )
    assert resp.status_code == 201, resp.text
    pkg = resp.json()
    assert pkg["name"] == "Superhero Party"
    assert pkg["per_head_price_cents"] == 3500
    assert pkg["deposit_pct"] == 30
    assert pkg["status"] == "active"

    public = client.get(f"/api/v1/parties/orgs/{org_id}/packages").json()
    assert any(p["id"] == pkg["id"] for p in public)


def test_create_package_requires_membership(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    resp = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(outsider),
        json=_package_body(venue_id),
    )
    assert resp.status_code == 403


def test_package_venue_must_belong_to_org(client: TestClient) -> None:
    owner, other = _signup(client), _signup(client)
    org_id, _venue = _org_with_venue(client, owner)
    _other_org, other_venue = _org_with_venue(client, other)  # a venue in a different org
    resp = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(other_venue),
    )
    assert resp.status_code == 404


def test_headcount_band_rejected(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    resp = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id, min_headcount=20, max_headcount=8),
    )
    assert resp.status_code == 400


def test_slots_created_and_publicly_listed(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id),
    ).json()

    resp = client.post(
        f"/api/v1/parties/packages/{pkg['id']}/slots", headers=_auth(owner),
        json={"slots": [
            {"starts_at": "2026-11-07T04:00:00Z", "ends_at": "2026-11-07T06:00:00Z"},
            {"starts_at": "2026-11-08T04:00:00Z", "ends_at": "2026-11-08T06:00:00Z"},
        ]},
    )
    assert resp.status_code == 201
    assert len(resp.json()) == 2

    public = client.get(f"/api/v1/parties/packages/{pkg['id']}/slots").json()
    assert len(public) == 2
    assert all(s["status"] == "available" for s in public)


def test_slot_end_before_start_rejected(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id),
    ).json()
    resp = client.post(
        f"/api/v1/parties/packages/{pkg['id']}/slots", headers=_auth(owner),
        json={"slots": [{"starts_at": "2026-11-07T06:00:00Z", "ends_at": "2026-11-07T04:00:00Z"}]},
    )
    assert resp.status_code == 422


def test_archive_removes_from_public_listing(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id),
    ).json()

    client.post(f"/api/v1/parties/packages/{pkg['id']}/archive", headers=_auth(owner))
    public = client.get(f"/api/v1/parties/orgs/{org_id}/packages").json()
    assert all(p["id"] != pkg["id"] for p in public)
    # But the provider still sees it in the manage view.
    manage = client.get(
        f"/api/v1/parties/orgs/{org_id}/packages/manage", headers=_auth(owner)
    ).json()
    assert any(p["id"] == pkg["id"] and p["status"] == "archived" for p in manage)


# --- B2: book a slot with a deposit -----------------------------------------

def _package_with_slot(client: TestClient, owner: str) -> tuple[str, str, str]:
    org_id, venue_id = _org_with_venue(client, owner)
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id),  # per_head 3500, band 8-20
    ).json()
    slot = client.post(
        f"/api/v1/parties/packages/{pkg['id']}/slots", headers=_auth(owner),
        json={"slots": [{"starts_at": "2026-11-07T04:00:00Z", "ends_at": "2026-11-07T06:00:00Z"}]},
    ).json()[0]
    return org_id, pkg["id"], slot["id"]


def test_book_slot_creates_deposit_and_holds_slot(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _org, pkg_id, slot_id = _package_with_slot(client, owner)

    resp = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(guardian),
        json={"headcount": 10},
    )
    assert resp.status_code == 201, resp.text
    b = resp.json()
    # 10 × $35 = $350 total; 30% deposit = $105; balance $245 (ADR-0007).
    assert (b["total_cents"], b["deposit_cents"], b["balance_cents"]) == (35000, 10500, 24500)
    assert b["status"] == "pending_deposit"
    assert b["client_secret"]  # for the deposit Payment Element

    # The slot is held → no longer publicly available.
    assert client.get(f"/api/v1/parties/packages/{pkg_id}/slots").json() == []


def test_deposit_webhook_confirms_booking_and_books_slot(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    _org, _pkg, slot_id = _package_with_slot(client, owner)
    booking_id = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(guardian),
        json={"headcount": 10},
    ).json()["id"]

    ack = _post_pi_event(
        client, event_id="evt_pd_ok", event_type="payment_intent.succeeded",
        intent_id=_deposit_pi(db, booking_id),
    )
    assert ack["status"] == "ok"
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None and booking.status is PartyBookingStatus.confirmed


def test_capacity_one_second_booking_conflicts(client: TestClient) -> None:
    owner, g1, g2 = _signup(client), _signup(client), _signup(client)
    _org, _pkg, slot_id = _package_with_slot(client, owner)
    first = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(g1), json={"headcount": 10}
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(g2), json={"headcount": 12}
    )
    assert second.status_code == 409  # slot already held (INV-1)


def test_headcount_out_of_band_rejected(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _org, _pkg, slot_id = _package_with_slot(client, owner)
    resp = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(guardian),
        json={"headcount": 50},  # band is 8-20
    )
    assert resp.status_code == 400


def test_deposit_canceled_releases_slot(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    _org, pkg_id, slot_id = _package_with_slot(client, owner)
    booking_id = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(guardian),
        json={"headcount": 10},
    ).json()["id"]

    ack = _post_pi_event(
        client, event_id="evt_pd_cx", event_type="payment_intent.canceled",
        intent_id=_deposit_pi(db, booking_id),
    )
    assert ack["status"] == "ok"
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None and booking.status is PartyBookingStatus.cancelled
    # Slot is bookable again.
    assert len(client.get(f"/api/v1/parties/packages/{pkg_id}/slots").json()) == 1


def test_abandoned_deposit_sweep_releases_the_slot(client: TestClient, db: Session) -> None:
    """A deposit that never completes leaves the slot held; the sweep frees it (INV-1)."""
    owner, guardian = _signup(client), _signup(client)
    _org, pkg_id, slot_id = _package_with_slot(client, owner)
    booking_id = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(guardian),
        json={"headcount": 10},
    ).json()["id"]
    assert client.get(f"/api/v1/parties/packages/{pkg_id}/slots").json() == []  # held

    later = datetime.now(UTC) + timedelta(seconds=1300)  # past the 1200s checkout window
    swept = parties_service.sweep_abandoned_deposits(db, gateway=FakeGateway(), now=later)
    assert swept == 1
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None and booking.status is PartyBookingStatus.cancelled
    assert len(client.get(f"/api/v1/parties/packages/{pkg_id}/slots").json()) == 1  # freed
    # Idempotent.
    assert parties_service.sweep_abandoned_deposits(db, gateway=FakeGateway(), now=later) == 0


# --- B3: T-7d balance auto-charge + auto-cancel -----------------------------

# Party slot starts 2026-11-07T04:00Z. Defaults: offset 7d (window opens 2026-10-31T04:00Z),
# cutoff 72h (2026-11-04T04:00Z).
BEFORE_WINDOW = datetime(2026, 10, 20, tzinfo=UTC)
IN_WINDOW = datetime(2026, 11, 1, tzinfo=UTC)
PAST_CUTOFF = datetime(2026, 11, 5, tzinfo=UTC)


class _DecliningGateway(FakeGateway):
    def charge_saved_card(self, **kw: object) -> PaymentIntentResult:
        return PaymentIntentResult(id="pi_decl", client_secret="", status="requires_payment_method")


class _RaisingGateway(FakeGateway):
    def charge_saved_card(self, **kw: object) -> PaymentIntentResult:
        raise RuntimeError("gateway blew up")


def _run_balances(db: Session, gw: FakeGateway, now: datetime) -> int:
    return parties_service.process_party_balances(
        db, gateway=gw, email_gateway=FakeEmailGateway(), now=now
    )


def _book_and_confirm(client: TestClient, db: Session, owner: str, guardian: str) -> str:
    _org, _pkg, slot_id = _package_with_slot(client, owner)
    booking_id = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(guardian), json={"headcount": 10}
    ).json()["id"]
    _post_pi_event(
        client, event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="payment_intent.succeeded", intent_id=_deposit_pi(db, booking_id),
    )
    return booking_id


def test_balance_not_charged_before_window(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    booking_id = _book_and_confirm(client, db, owner, guardian)
    assert _run_balances(db, FakeGateway(), BEFORE_WINDOW) == 0
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None and not booking.balance_captured


def test_balance_charged_in_window_accrues_payout(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    org_id, _venue = _org_with_venue(client, owner)  # ensure owner is a member for payouts read
    booking_id = _book_and_confirm(client, db, owner, guardian)
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None
    org_id = str(booking.organisation_id)

    processed = _run_balances(db, FakeGateway(), IN_WINDOW)
    assert processed == 1
    db.refresh(booking)
    assert booking.balance_captured is True
    assert booking.payout_id is not None
    # $350 total − 10% fee − GST = $311.50 net (ADR-0002).
    payouts = client.get(
        "/api/v1/payments/payouts", headers=_auth(owner), params={"organisation_id": org_id}
    ).json()
    assert any(p["amount_cents"] == 31150 for p in payouts)

    # Idempotent: already captured → not processed again.
    assert _run_balances(db, FakeGateway(), IN_WINDOW) == 0


def test_unpaid_balance_auto_cancels_and_refunds_deposit(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    booking_id = _book_and_confirm(client, db, owner, guardian)

    processed = _run_balances(db, FakeGateway(), PAST_CUTOFF)
    assert processed == 1
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None and booking.status is PartyBookingStatus.cancelled
    assert not booking.balance_captured
    # Deposit refunded (ADR-0010).
    deposit = db.get(Payment, booking.deposit_payment_id)
    assert deposit is not None and deposit.status.value == "refunded"


def test_declining_card_retries_in_window_then_cancels_at_cutoff(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    booking_id = _book_and_confirm(client, db, owner, guardian)
    gw = _DecliningGateway()

    # Two in-window attempts (≥48h apart) both decline — booking stays confirmed, uncaptured.
    _run_balances(db, gw, datetime(2026, 11, 1, tzinfo=UTC))
    _run_balances(db, gw, datetime(2026, 11, 3, tzinfo=UTC))
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None and booking.balance_attempts == 2 and not booking.balance_captured
    assert booking.status is PartyBookingStatus.confirmed

    # Past the T-72h cutoff, still unpaid → auto-cancel + refund the deposit (ADR-0008/0010).
    _run_balances(db, gw, PAST_CUTOFF)
    db.refresh(booking)
    assert booking.status is PartyBookingStatus.cancelled
    deposit = db.get(Payment, booking.deposit_payment_id)
    assert deposit is not None and deposit.status.value == "refunded"


def test_charge_exception_is_isolated_not_wedged(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    """An unexpected error charging one booking must not abort the whole tick (savepoint)."""
    owner, guardian = _signup(client), _signup(client)
    booking_id = _book_and_confirm(client, db, owner, guardian)
    # Must not raise out of the tick.
    parties_service.process_party_balances(
        db, gateway=_RaisingGateway(), email_gateway=FakeEmailGateway(), now=IN_WINDOW
    )
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None
    assert not booking.balance_captured and booking.status is PartyBookingStatus.confirmed
