"""Booking checkout: the hold → pending → confirmed/cancelled state machine,
cart-level idempotency, the application fee, and validation guards."""

import uuid
from typing import Any

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _published_session(
    client: TestClient,
    owner_token: str,
    *,
    capacity: int = 5,
    price_cents: int = 5000,
    age_min: int = 5,
    age_max: int = 12,
) -> str:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner_token), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(owner_token),
        json={"organisation_id": org_id, "name": "Hall"},
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(owner_token),
        json={"organisation_id": org_id, "title": "Camp", "category": "art"},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(owner_token),
        json={
            "venue_id": venue_id,
            "starts_at": "2026-09-30T09:00:00Z",
            "ends_at": "2026-09-30T15:00:00Z",
            "capacity": capacity,
            "price_cents": price_cents,
            "age_min": age_min,
            "age_max": age_max,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner_token))
    return session_id


def _hold(client: TestClient, guardian: str, session_id: str, qty: int = 1) -> str:
    return client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": qty},
    ).json()["id"]


def _add_child(client: TestClient, guardian: str, *, dob: str = "2019-01-01") -> str:
    return client.post(
        "/api/v1/identity/children",
        headers=_auth(guardian),
        json={"first_name": "Kid", "date_of_birth": dob},
    ).json()["id"]


def _remaining(client: TestClient, session_id: str) -> int:
    return client.get(f"/api/v1/inventory/sessions/{session_id}/availability").json()[
        "seats_remaining"
    ]


def _checkout(
    client: TestClient, guardian: str, hold_id: str, child_ids: list[str], key: str
) -> Any:
    return client.post(
        "/api/v1/booking/checkout",
        headers=_auth(guardian),
        json={
            "idempotency_key": key,
            "items": [
                {"hold_id": hold_id, "children": [{"child_id": c} for c in child_ids]}
            ],
        },
    )


def test_checkout_confirm_consumes_hold_and_keeps_seat(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=3, price_cents=5000)
    hold_id = _hold(client, guardian, session_id)
    child_id = _add_child(client, guardian)
    assert _remaining(client, session_id) == 2  # one seat held

    order = _checkout(client, guardian, hold_id, [child_id], key=f"key-{uuid.uuid4().hex}")
    assert order.status_code == 201, order.text
    body = order.json()
    assert body["status"] == "pending"
    assert body["amount_cents"] == 5000
    assert body["application_fee_cents"] == 500  # 10%
    assert len(body["bookings"]) == 1
    assert body["bookings"][0]["status"] == "pending"
    payment_id = body["payment_id"]

    confirmed = client.post(
        f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian)
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "succeeded"
    assert confirmed.json()["bookings"][0]["status"] == "confirmed"
    # Seat stays taken after confirmation.
    assert _remaining(client, session_id) == 2


def test_cancel_releases_the_seat(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=1)
    hold_id = _hold(client, guardian, session_id)
    child_id = _add_child(client, guardian)
    assert _remaining(client, session_id) == 0  # fully held

    order = _checkout(client, guardian, hold_id, [child_id], key=f"key-{uuid.uuid4().hex}")
    payment_id = order.json()["payment_id"]

    cancelled = client.post(
        f"/api/v1/booking/payments/{payment_id}/cancel", headers=_auth(guardian)
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "failed"
    assert cancelled.json()["bookings"][0]["status"] == "cancelled"
    # Seat freed again.
    assert _remaining(client, session_id) == 1


def test_checkout_is_idempotent(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=3)
    hold_id = _hold(client, guardian, session_id)
    child_id = _add_child(client, guardian)
    key = f"key-{uuid.uuid4().hex}"

    first = _checkout(client, guardian, hold_id, [child_id], key=key)
    second = _checkout(client, guardian, hold_id, [child_id], key=key)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["payment_id"] == second.json()["payment_id"]
    # Only one seat consumed despite two identical calls.
    assert _remaining(client, session_id) == 2


def test_child_count_must_match_seats(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=5)
    hold_id = _hold(client, guardian, session_id, qty=2)  # two seats
    child_id = _add_child(client, guardian)  # only one child
    resp = _checkout(client, guardian, hold_id, [child_id], key=f"key-{uuid.uuid4().hex}")
    assert resp.status_code == 400


def test_age_outside_band_is_rejected(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    # Session for ages 5–12; child born 2024 → ~2 years old at the 2026 session.
    session_id = _published_session(client, owner, age_min=5, age_max=12)
    hold_id = _hold(client, guardian, session_id)
    toddler = _add_child(client, guardian, dob="2024-01-01")
    resp = _checkout(client, guardian, hold_id, [toddler], key=f"key-{uuid.uuid4().hex}")
    assert resp.status_code == 400


def test_cannot_checkout_someone_elses_hold(client: TestClient) -> None:
    owner, guardian_a, guardian_b = _signup(client), _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=3)
    hold_id = _hold(client, guardian_a, session_id)  # held by A
    child_b = _add_child(client, guardian_b)
    resp = _checkout(client, guardian_b, hold_id, [child_b], key=f"key-{uuid.uuid4().hex}")
    assert resp.status_code == 409


def test_bookings_list_shows_confirmed_order(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=2)
    hold_id = _hold(client, guardian, session_id)
    child_id = _add_child(client, guardian)
    order = _checkout(client, guardian, hold_id, [child_id], key=f"key-{uuid.uuid4().hex}")
    client.post(
        f"/api/v1/booking/payments/{order.json()['payment_id']}/confirm",
        headers=_auth(guardian),
    )
    mine = client.get("/api/v1/booking/bookings", headers=_auth(guardian))
    assert mine.status_code == 200
    rows = mine.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "confirmed"
    assert rows[0]["children"][0]["child_id"] == child_id
