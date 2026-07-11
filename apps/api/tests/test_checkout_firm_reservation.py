"""Firm-reservation checkout settlement (ADR-0005 §1): a checked-out seat is committed
and stays counted until an explicit terminal outcome — it is NOT reclaimed by the TTL
sweep, and only the abandoned-checkout sweep (or confirm/cancel) resolves it. INV-1."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.booking.core import service as booking_service
from juggle.modules.inventory.core import service as inventory_service
from juggle.modules.inventory.core.models import SeatHold, SeatHoldStatus
from juggle.modules.payments.core.gateway import FakeGateway
from juggle.modules.payments.core.models import Payment, PaymentStatus


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _published_session(client: TestClient, owner: str, *, capacity: int = 1) -> str:
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
            "starts_at": "2026-09-30T09:00:00Z",
            "ends_at": "2026-09-30T15:00:00Z",
            "capacity": capacity,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return session_id


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


def _remaining(client: TestClient, session_id: str) -> int:
    return client.get(
        f"/api/v1/inventory/sessions/{session_id}/availability"
    ).json()["seats_remaining"]


def _payment_status(db: Session, payment_id: str) -> PaymentStatus:
    payment = db.scalar(select(Payment).where(Payment.id == uuid.UUID(payment_id)))
    assert payment is not None
    return payment.status


def test_checkout_returns_a_client_secret(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner)
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
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()
    assert order["client_secret"]  # the Payment Element needs it to confirm


def test_reserved_seat_survives_the_ttl_sweep(client: TestClient, db: Session) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=1)
    payment_id = _checkout(client, guardian, session_id)
    assert _remaining(client, session_id) == 0

    # A TTL sweep far in the future must NOT free a firm reservation (ADR-0005 §1).
    reclaimed = inventory_service.reclaim_all_expired(
        db, now=datetime.now(UTC) + timedelta(hours=6)
    )
    assert reclaimed == 0
    assert _remaining(client, session_id) == 0
    assert _payment_status(db, payment_id) is PaymentStatus.pending


def test_abandoned_sweep_frees_the_seat_and_fails_the_payment(
    client: TestClient, db: Session
) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=1)
    payment_id = _checkout(client, guardian, session_id)
    assert _remaining(client, session_id) == 0

    later = datetime.now(UTC) + timedelta(seconds=1300)  # past the 1200s checkout window
    swept = booking_service.sweep_abandoned_checkouts(db, gateway=FakeGateway(), now=later)
    assert swept == 1
    assert _remaining(client, session_id) == 1  # seat returned
    assert _payment_status(db, payment_id) is PaymentStatus.failed

    # Idempotent: a second sweep finds nothing still pending.
    assert booking_service.sweep_abandoned_checkouts(db, gateway=FakeGateway(), now=later) == 0


def test_confirmed_order_is_never_swept(client: TestClient, db: Session) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=1)
    payment_id = _checkout(client, guardian, session_id)
    client.post(f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian))
    assert _remaining(client, session_id) == 0

    later = datetime.now(UTC) + timedelta(seconds=1300)
    assert booking_service.sweep_abandoned_checkouts(db, gateway=FakeGateway(), now=later) == 0
    assert _remaining(client, session_id) == 0  # confirmed seat stays taken
    assert _payment_status(db, payment_id) is PaymentStatus.succeeded


def test_double_force_release_does_not_underflow_seats(
    client: TestClient, db: Session
) -> None:
    """A provider cancel racing the abandoned sweep can call force_release twice on the
    same reserved hold; the second must be a no-op, not a second decrement (INV-1)."""
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=1)
    _checkout(client, guardian, session_id)
    hold = db.scalar(
        select(SeatHold).where(
            SeatHold.session_id == uuid.UUID(session_id),
            SeatHold.status == SeatHoldStatus.reserved,
        )
    )
    assert hold is not None

    inventory_service.force_release(db, hold_id=hold.id)
    assert _remaining(client, session_id) == 1
    inventory_service.force_release(db, hold_id=hold.id)  # racing second caller
    assert _remaining(client, session_id) == 1  # not 2 — no double-decrement


def test_reserve_refuses_a_reclaimed_seat(client: TestClient, db: Session) -> None:
    """If a browsing hold's TTL lapses and the seat is reclaimed, reserve_hold must
    refuse (return False) rather than resurrect a seat that was already given back."""
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=1)
    hold_id = client.post(
        "/api/v1/inventory/holds", headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]

    hold = db.scalar(select(SeatHold).where(SeatHold.id == uuid.UUID(hold_id)))
    assert hold is not None
    hold.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()
    assert inventory_service.reclaim_all_expired(db, now=datetime.now(UTC)) == 1

    assert inventory_service.reserve_hold(db, hold_id=uuid.UUID(hold_id)) is False
    assert _remaining(client, session_id) == 1  # seat stays free, not re-reserved


def test_cancel_frees_a_reserved_seat(client: TestClient, db: Session) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=1)
    payment_id = _checkout(client, guardian, session_id)
    assert _remaining(client, session_id) == 0

    cancelled = client.post(
        f"/api/v1/booking/payments/{payment_id}/cancel", headers=_auth(guardian)
    )
    assert cancelled.json()["status"] == "failed"
    assert _remaining(client, session_id) == 1
