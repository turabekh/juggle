"""Provider-initiated session cancellation: refunds paid families, releases all
seats, cancels bookings, and dents the org's reliability score."""

import uuid

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_and_session(
    client: TestClient, owner_token: str, *, capacity: int = 3
) -> tuple[str, str]:
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
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner_token))
    return org_id, session_id


def _confirmed_booking(client: TestClient, guardian: str, session_id: str) -> str:
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children",
        headers=_auth(guardian),
        json={"first_name": "Kid", "date_of_birth": "2018-01-01"},
    ).json()["id"]
    order = client.post(
        "/api/v1/booking/checkout",
        headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()
    client.post(f"/api/v1/booking/payments/{order['payment_id']}/confirm", headers=_auth(guardian))
    return order["payment_id"]


def _remaining(client: TestClient, session_id: str) -> int:
    return client.get(f"/api/v1/inventory/sessions/{session_id}/availability").json()[
        "seats_remaining"
    ]


def test_cancel_refunds_releases_and_dings_reliability(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    org_id, session_id = _org_and_session(client, owner, capacity=3)
    payment_id = _confirmed_booking(client, guardian, session_id)
    assert _remaining(client, session_id) == 2  # one confirmed seat

    resp = client.post(
        f"/api/v1/booking/sessions/{session_id}/cancel", headers=_auth(owner)
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["cancelled_bookings"] == 1
    assert result["refunded_payments"] == 1
    assert result["reliability_score"] == 0.9  # 1.0 - 0.1 penalty

    # Payment refunded.
    payment = client.get(f"/api/v1/payments/{payment_id}", headers=_auth(guardian)).json()
    assert payment["status"] == "refunded"

    # Seat released.
    assert _remaining(client, session_id) == 3

    # Guardian's booking shows refunded.
    mine = client.get("/api/v1/booking/bookings", headers=_auth(guardian)).json()
    assert mine[0]["status"] == "refunded"


def test_only_owner_can_cancel_a_session(client: TestClient) -> None:
    owner, staff_token = _signup(client), _signup(client)
    org_id, session_id = _org_and_session(client, owner)
    # Make the second user staff (not owner) of the org.
    staff_id = uuid.UUID(
        client.get("/api/v1/identity/me", headers=_auth(staff_token)).json()["id"]
    )
    client.post(
        f"/api/v1/org/{org_id}/members",
        headers=_auth(owner),
        json={"user_account_id": str(staff_id), "role": "staff"},
    )
    resp = client.post(
        f"/api/v1/booking/sessions/{session_id}/cancel", headers=_auth(staff_token)
    )
    assert resp.status_code == 403


def test_outsider_cannot_cancel(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    resp = client.post(
        f"/api/v1/booking/sessions/{session_id}/cancel", headers=_auth(outsider)
    )
    assert resp.status_code == 403


def test_cancel_is_idempotent(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    _confirmed_booking(client, guardian, session_id)

    first = client.post(
        f"/api/v1/booking/sessions/{session_id}/cancel", headers=_auth(owner)
    ).json()
    assert first["cancelled_bookings"] == 1

    second = client.post(
        f"/api/v1/booking/sessions/{session_id}/cancel", headers=_auth(owner)
    ).json()
    assert second["cancelled_bookings"] == 0  # nothing left to cancel
    assert second["reliability_score"] == 0.9  # not dinged twice
