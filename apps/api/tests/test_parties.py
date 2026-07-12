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


def test_public_package_detail_enriched(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id),
    ).json()

    resp = client.get(f"/api/v1/parties/packages/{pkg['id']}")
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["id"] == pkg["id"]
    assert detail["organisation_name"]
    assert detail["venue_name"]
    assert detail["deposit_pct_effective"] == 30  # config default (ADR-0007)


def test_marketplace_lists_only_approved_active_packages(
    client: TestClient, db: Session
) -> None:
    from juggle.modules.org.core import service as org_service
    from juggle.modules.org.core.models import OrgStatus

    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id),
    ).json()

    # Pending org ⇒ not in the public marketplace list.
    assert all(p["id"] != pkg["id"] for p in client.get("/api/v1/parties/packages").json())

    # Approve ⇒ it appears, enriched with the provider/venue names.
    org_service.set_status(db, uuid.UUID(org_id), OrgStatus.approved)
    db.flush()
    listed = client.get("/api/v1/parties/packages").json()
    card = next((p for p in listed if p["id"] == pkg["id"]), None)
    assert card is not None
    assert card["organisation_name"] and card["venue_name"]
    assert card["deposit_pct_effective"] == 30

    # Archived ⇒ drops back out.
    client.post(f"/api/v1/parties/packages/{pkg['id']}/archive", headers=_auth(owner))
    assert all(p["id"] != pkg["id"] for p in client.get("/api/v1/parties/packages").json())


def test_public_package_detail_hidden_when_archived(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id),
    ).json()
    client.post(f"/api/v1/parties/packages/{pkg['id']}/archive", headers=_auth(owner))

    assert client.get(f"/api/v1/parties/packages/{pkg['id']}").status_code == 404


# --- B2: book a slot with a deposit -----------------------------------------

def _package_with_slot(
    client: TestClient, owner: str, *, deposit_pct: int | None = None
) -> tuple[str, str, str]:
    org_id, venue_id = _org_with_venue(client, owner)
    body = _package_body(venue_id)  # per_head 3500, band 8-20
    if deposit_pct is not None:
        body["deposit_pct"] = deposit_pct
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner), json=body,
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


def _book_and_confirm(
    client: TestClient, db: Session, owner: str, guardian: str, *, deposit_pct: int | None = None
) -> str:
    _org, _pkg, slot_id = _package_with_slot(client, owner, deposit_pct=deposit_pct)
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


def test_dev_confirm_settles_the_deposit(client: TestClient, db: Session) -> None:
    """Dev/FakeGateway: confirm the deposit synchronously (no webhook)."""
    owner, guardian = _signup(client), _signup(client)
    _org, _pkg, slot_id = _package_with_slot(client, owner)
    booking_id = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(guardian), json={"headcount": 10}
    ).json()["id"]
    resp = client.post(
        f"/api/v1/parties/bookings/{booking_id}/dev-confirm", headers=_auth(guardian)
    )
    assert resp.status_code == 200 and resp.json()["status"] == "confirmed"
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None and booking.status is PartyBookingStatus.confirmed


# --- B4: guest-count adjustment + cancellation ------------------------------

def test_adjust_headcount_recomputes_total(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    booking_id = _book_and_confirm(client, db, owner, guardian)  # 10 heads
    resp = client.post(
        f"/api/v1/parties/bookings/{booking_id}/adjust", headers=_auth(guardian),
        json={"headcount": 12},
    )
    assert resp.status_code == 200, resp.text
    b = resp.json()
    # 12 × $35 = $420 total; deposit ($105) unchanged; balance $315.
    assert (b["headcount"], b["total_cents"], b["deposit_cents"], b["balance_cents"]) == (
        12, 42000, 10500, 31500,
    )


def test_adjust_down_below_deposit_refunds_excess(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    # 100% deposit: 10 heads → $350 all paid up front. Reduce to 8 → refund the $70 excess.
    booking_id = _book_and_confirm(client, db, owner, guardian, deposit_pct=100)
    resp = client.post(
        f"/api/v1/parties/bookings/{booking_id}/adjust", headers=_auth(guardian),
        json={"headcount": 8},
    )
    assert resp.status_code == 200
    b = resp.json()
    assert (b["total_cents"], b["deposit_cents"], b["balance_cents"]) == (28000, 28000, 0)
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None
    deposit = db.get(Payment, booking.deposit_payment_id)
    assert deposit is not None and deposit.refunded_cents == 7000


def test_adjust_blocked_after_balance_captured(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    booking_id = _book_and_confirm(client, db, owner, guardian)
    _run_balances(db, FakeGateway(), IN_WINDOW)  # capture the balance
    resp = client.post(
        f"/api/v1/parties/bookings/{booking_id}/adjust", headers=_auth(guardian),
        json={"headcount": 12},
    )
    assert resp.status_code == 409


def test_adjust_by_non_owner_forbidden(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian, other = _signup(client), _signup(client), _signup(client)
    booking_id = _book_and_confirm(client, db, owner, guardian)
    resp = client.post(
        f"/api/v1/parties/bookings/{booking_id}/adjust", headers=_auth(other),
        json={"headcount": 12},
    )
    assert resp.status_code == 403


def test_provider_cancel_refunds_deposit_and_releases_slot(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    _org, pkg_id, slot_id = _package_with_slot(client, owner)
    booking_id = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(guardian), json={"headcount": 10}
    ).json()["id"]
    _post_pi_event(
        client, event_id="evt_pc", event_type="payment_intent.succeeded",
        intent_id=_deposit_pi(db, booking_id),
    )
    resp = client.post(
        f"/api/v1/parties/bookings/{booking_id}/cancel", headers=_auth(owner)  # provider
    )
    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None
    deposit = db.get(Payment, booking.deposit_payment_id)
    assert deposit is not None and deposit.status.value == "refunded"  # 100% incl. deposit
    assert len(client.get(f"/api/v1/parties/packages/{pkg_id}/slots").json()) == 1  # slot freed


def test_parent_cancel_before_capture_keeps_deposit(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    booking_id = _book_and_confirm(client, db, owner, guardian)
    client.post(f"/api/v1/parties/bookings/{booking_id}/cancel", headers=_auth(guardian))
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None and booking.status is PartyBookingStatus.cancelled
    deposit = db.get(Payment, booking.deposit_payment_id)
    assert deposit is not None and deposit.status.value == "succeeded"  # deposit kept


def test_parent_cancel_after_capture_refunds_balance_and_claws_back_payout(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    owner, guardian = _signup(client), _signup(client)
    booking_id = _book_and_confirm(client, db, owner, guardian)
    org_id = str(db.get(PartyBooking, uuid.UUID(booking_id)).organisation_id)  # type: ignore[union-attr]
    _run_balances(db, FakeGateway(), IN_WINDOW)  # capture balance → payout net 31150

    client.post(f"/api/v1/parties/bookings/{booking_id}/cancel", headers=_auth(guardian))
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None and booking.status is PartyBookingStatus.cancelled
    # Balance ($245) refunded, deposit ($105) kept.
    balance = db.get(Payment, booking.balance_payment_id)
    assert balance is not None and balance.status.value == "refunded"
    deposit = db.get(Payment, booking.deposit_payment_id)
    assert deposit is not None and deposit.status.value == "succeeded"
    # Payout clawed back to the deposit's net (net 24500 reversed from 31150 → 9345).
    payouts = client.get(
        "/api/v1/payments/payouts", headers=_auth(owner), params={"organisation_id": org_id}
    ).json()
    assert any(p["amount_cents"] == 9345 for p in payouts)


def test_parent_cancel_clawback_is_exact_under_rounding(
    client: TestClient, db: Session, webhook_secret: None
) -> None:
    """A rounding-edge split (net is non-additive): the payout must end at net(deposit) exactly,
    not net(total)−net(balance) which would be a cent off."""
    owner, guardian = _signup(client), _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    # per_head 501 × 10 = $50.10 total; 50% deposit = 2505; balance 2505.
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json={"venue_id": venue_id, "name": "Edge", "per_head_price_cents": 501,
              "min_headcount": 8, "max_headcount": 20, "deposit_pct": 50},
    ).json()
    slot = client.post(
        f"/api/v1/parties/packages/{pkg['id']}/slots", headers=_auth(owner),
        json={"slots": [{"starts_at": "2026-11-07T04:00:00Z", "ends_at": "2026-11-07T06:00:00Z"}]},
    ).json()[0]
    booking_id = client.post(
        f"/api/v1/parties/slots/{slot['id']}/book", headers=_auth(guardian), json={"headcount": 10}
    ).json()["id"]
    _post_pi_event(
        client, event_id="evt_edge", event_type="payment_intent.succeeded",
        intent_id=_deposit_pi(db, booking_id),
    )
    _run_balances(db, FakeGateway(), IN_WINDOW)  # capture → payout net(5010)=4459

    client.post(f"/api/v1/parties/bookings/{booking_id}/cancel", headers=_auth(guardian))
    payouts = client.get(
        "/api/v1/payments/payouts", headers=_auth(owner), params={"organisation_id": org_id}
    ).json()
    # net(deposit 2505) = 2505 − 250 − 25 = 2230  (the naive net(balance) path would leave 2229).
    assert any(p["amount_cents"] == 2230 for p in payouts)


def test_provider_cancel_pending_deposit_does_not_refund_uncaptured(
    client: TestClient, db: Session
) -> None:
    """Provider-cancelling before the deposit is captured must NOT refund the uncaptured PI."""
    owner, guardian = _signup(client), _signup(client)
    _org, pkg_id, slot_id = _package_with_slot(client, owner)
    booking_id = client.post(
        f"/api/v1/parties/slots/{slot_id}/book", headers=_auth(guardian), json={"headcount": 10}
    ).json()["id"]  # pending_deposit — no webhook yet

    resp = client.post(f"/api/v1/parties/bookings/{booking_id}/cancel", headers=_auth(owner))
    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"
    booking = db.get(PartyBooking, uuid.UUID(booking_id))
    assert booking is not None
    deposit = db.get(Payment, booking.deposit_payment_id)
    assert deposit is not None and deposit.status.value == "pending"  # NOT refunded
    assert len(client.get(f"/api/v1/parties/packages/{pkg_id}/slots").json()) == 1  # slot freed
