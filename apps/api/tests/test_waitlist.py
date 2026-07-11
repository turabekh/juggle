"""Waitlist (PRD §7.7): join only when sold out; a freed seat is auto-offered to
the front of the FIFO queue with a claim-window hold; unclaimed offers expire and
pass to the next family; claiming is a normal checkout against the offer hold.

Reconciliation has no scheduler, so tests trigger it the way the app does — via a
guardian reading their waitlist, the provider viewing the queue, or the admin
ops sweep. Seat-freeing uses a cancelled pending booking / admin refund.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# A near-future session so it is bookable and an 8-year-old is in range.
STARTS = "2026-12-01T09:00:00Z"
ENDS = "2026-12-01T15:00:00Z"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_and_session(client: TestClient, owner: str, *, capacity: int = 1) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(owner),
        json={"organisation_id": org_id, "name": "Hall"},
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(owner),
        json={"organisation_id": org_id, "title": "Camp", "category": "art"},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(owner),
        json={
            "venue_id": venue_id,
            "starts_at": STARTS,
            "ends_at": ENDS,
            "capacity": capacity,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return org_id, session_id


def _child(client: TestClient, guardian: str) -> str:
    return client.post(
        "/api/v1/identity/children",
        headers=_auth(guardian),
        json={"first_name": "Robin", "date_of_birth": "2018-06-01"},
    ).json()["id"]


def _checkout(client: TestClient, guardian: str, session_id: str) -> str:
    """Hold + checkout one seat (pending). Returns the payment id."""
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = _child(client, guardian)
    return client.post(
        "/api/v1/booking/checkout",
        headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()["payment_id"]


def _fill_seat(client: TestClient, session_id: str) -> tuple[str, str]:
    """Occupy the single seat with a pending booking. Returns (guardian, payment_id)."""
    g = _signup(client)
    payment_id = _checkout(client, g, session_id)
    return g, payment_id


def _join(client: TestClient, guardian: str, session_id: str):
    return client.post(
        "/api/v1/waitlist", headers=_auth(guardian), json={"session_id": session_id}
    )


def _mine(client: TestClient, guardian: str) -> list[dict]:
    return client.get("/api/v1/waitlist/mine", headers=_auth(guardian)).json()


# --- join gate ---------------------------------------------------------------


def test_cannot_join_when_seats_available(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, capacity=3)
    resp = _join(client, guardian, session_id)
    assert resp.status_code == 409  # book it directly instead


def test_join_when_sold_out(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, capacity=1)
    _fill_seat(client, session_id)  # sells the only seat
    resp = _join(client, guardian, session_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "waiting"
    assert body["position"] == 1


def test_cannot_join_twice(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, capacity=1)
    _fill_seat(client, session_id)
    assert _join(client, guardian, session_id).status_code == 201
    assert _join(client, guardian, session_id).status_code == 409


def test_position_is_fifo(client: TestClient) -> None:
    owner, first, second = _signup(client), _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, capacity=1)
    _fill_seat(client, session_id)
    _join(client, first, session_id)
    _join(client, second, session_id)
    assert _mine(client, first)[0]["position"] == 1
    assert _mine(client, second)[0]["position"] == 2


# --- offer on a freed seat ---------------------------------------------------


def test_freed_seat_is_offered_to_front(client: TestClient) -> None:
    owner, waiter = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, capacity=1)
    holder, payment_id = _fill_seat(client, session_id)
    _join(client, waiter, session_id)

    # Holder cancels their pending booking → the seat frees up.
    client.post(f"/api/v1/booking/payments/{payment_id}/cancel", headers=_auth(holder))

    # Waiter reads their waitlist → reconciliation offers them the seat.
    mine = _mine(client, waiter)
    assert len(mine) == 1
    assert mine[0]["status"] == "offered"
    assert mine[0]["offer_hold_id"] is not None
    assert mine[0]["offer_expires_at"] is not None

    # An offer notification was logged for the waiter.
    notes = client.get("/api/v1/notifications", headers=_auth(waiter)).json()
    assert any(n["kind"] == "waitlist_offer" for n in notes)


def test_claim_offer_via_checkout(client: TestClient) -> None:
    owner, waiter = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, capacity=1)
    holder, payment_id = _fill_seat(client, session_id)
    _join(client, waiter, session_id)
    client.post(f"/api/v1/booking/payments/{payment_id}/cancel", headers=_auth(holder))

    offer = _mine(client, waiter)[0]
    hold_id = offer["offer_hold_id"]

    # Claim = normal checkout against the offered hold, then confirm.
    child_id = _child(client, waiter)
    order = client.post(
        "/api/v1/booking/checkout",
        headers=_auth(waiter),
        json={
            "idempotency_key": f"claim-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    )
    assert order.status_code == 201, order.text
    pid = order.json()["payment_id"]
    assert (
        client.post(f"/api/v1/booking/payments/{pid}/confirm", headers=_auth(waiter)).status_code
        == 200
    )

    # The claimed entry drops off the active waitlist.
    assert _mine(client, waiter) == []


def test_leave_waitlist_releases_offer_to_next(client: TestClient) -> None:
    owner, first, second = _signup(client), _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, capacity=1)
    holder, payment_id = _fill_seat(client, session_id)
    _join(client, first, session_id)
    _join(client, second, session_id)
    client.post(f"/api/v1/booking/payments/{payment_id}/cancel", headers=_auth(holder))

    first_offer = _mine(client, first)[0]
    assert first_offer["status"] == "offered"

    # First leaves → their held seat is released and offered to second.
    entry_id = first_offer["id"]
    assert (
        client.delete(f"/api/v1/waitlist/{entry_id}", headers=_auth(first)).status_code == 204
    )
    assert _mine(client, first) == []

    second_mine = _mine(client, second)
    assert second_mine[0]["status"] == "offered"


def test_expired_offer_passes_to_next(client: TestClient, db: Session) -> None:
    from datetime import UTC, datetime, timedelta

    from juggle.modules.inventory.core.models import SeatHold

    owner, first, second = _signup(client), _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, capacity=1)
    holder, payment_id = _fill_seat(client, session_id)
    _join(client, first, session_id)
    _join(client, second, session_id)
    client.post(f"/api/v1/booking/payments/{payment_id}/cancel", headers=_auth(holder))

    first_offer = _mine(client, first)[0]  # reconcile → first offered
    assert first_offer["status"] == "offered"

    # Force the offer hold past its claim window, then run the ops sweep.
    hold = db.get(SeatHold, uuid.UUID(first_offer["offer_hold_id"]))
    assert hold is not None
    hold.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()

    admin_token = _make_admin_token(client, db)
    run = client.post("/api/v1/waitlist/process", headers=_auth(admin_token)).json()
    assert run["offers_expired"] >= 1

    assert _mine(client, first) == []  # first's offer expired (no longer active)
    assert _mine(client, second)[0]["status"] == "offered"  # passed to second


# --- provider + admin surfaces ----------------------------------------------


def test_provider_sees_queue_counts(client: TestClient) -> None:
    owner, outsider, waiter = _signup(client), _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, capacity=1)
    _fill_seat(client, session_id)
    _join(client, waiter, session_id)

    counts = client.get(f"/api/v1/waitlist/sessions/{session_id}", headers=_auth(owner))
    assert counts.status_code == 200
    assert counts.json()["waiting"] == 1

    assert (
        client.get(
            f"/api/v1/waitlist/sessions/{session_id}", headers=_auth(outsider)
        ).status_code
        == 403
    )


def test_process_is_admin_only(client: TestClient) -> None:
    guardian = _signup(client)
    assert client.post("/api/v1/waitlist/process", headers=_auth(guardian)).status_code == 403


def _make_admin_token(client: TestClient, db: Session) -> str:
    from sqlalchemy import select

    from juggle.modules.identity.core.models import UserAccount

    email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/v1/identity/signup", json={"email": email, "password": "supersecret"})
    user = db.scalar(select(UserAccount).where(UserAccount.email == email))
    assert user is not None
    user.is_admin = True
    db.flush()
    return client.post(
        "/api/v1/identity/login", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]
