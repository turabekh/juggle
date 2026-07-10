"""Notifications: confirming a booking emails a confirmation (logged) with an
.ics; cancelling a session notifies families; the guardian can see their log."""

import uuid

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _published_session(client: TestClient, owner: str, *, capacity: int = 3) -> tuple[str, str]:
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
        json={"organisation_id": org_id, "title": "Robotics Camp", "category": "stem"},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(owner),
        json={
            "venue_id": venue_id,
            "starts_at": "2026-09-30T01:00:00Z",
            "ends_at": "2026-09-30T07:00:00Z",
            "capacity": capacity,
            "price_cents": 5000,
            "age_min": 5,
            "age_max": 14,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return session_id, program_id


def _book_and_pay(client: TestClient, guardian: str, session_id: str) -> str:
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children",
        headers=_auth(guardian),
        json={"first_name": "Robin", "date_of_birth": "2018-01-01"},
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


def test_confirmation_notification_and_ics(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id, _ = _published_session(client, owner)
    payment_id = _book_and_pay(client, guardian, session_id)

    # A confirmation notification is logged for the guardian.
    notes = client.get("/api/v1/notifications", headers=_auth(guardian)).json()
    assert len(notes) == 1
    assert notes[0]["kind"] == "booking_confirmation"
    assert notes[0]["detail"]["sessions"] == 1

    # The order's calendar file is a valid .ics with the session.
    ics = client.get(
        f"/api/v1/booking/payments/{payment_id}/calendar.ics", headers=_auth(guardian)
    )
    assert ics.status_code == 200
    assert ics.headers["content-type"].startswith("text/calendar")
    body = ics.text
    assert "BEGIN:VCALENDAR" in body and "BEGIN:VEVENT" in body
    assert "SUMMARY:Robotics Camp" in body


def test_confirmation_is_not_resent_on_repeat_confirm(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id, _ = _published_session(client, owner)
    payment_id = _book_and_pay(client, guardian, session_id)
    # Confirm again (idempotent) — must not create a second notification.
    client.post(f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian))
    notes = client.get("/api/v1/notifications", headers=_auth(guardian)).json()
    assert len(notes) == 1


def test_cancellation_notifies_family(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id, _ = _published_session(client, owner)
    _book_and_pay(client, guardian, session_id)

    resp = client.post(f"/api/v1/booking/sessions/{session_id}/cancel", headers=_auth(owner))
    assert resp.status_code == 200

    notes = client.get("/api/v1/notifications", headers=_auth(guardian)).json()
    kinds = [n["kind"] for n in notes]
    assert "session_cancellation" in kinds
    cancel = next(n for n in notes if n["kind"] == "session_cancellation")
    assert cancel["detail"]["refunded"] is True


def test_notifications_are_private(client: TestClient) -> None:
    owner, guardian, other = _signup(client), _signup(client), _signup(client)
    session_id, _ = _published_session(client, owner)
    _book_and_pay(client, guardian, session_id)
    # Another user sees none of the guardian's notifications.
    assert client.get("/api/v1/notifications", headers=_auth(other)).json() == []
