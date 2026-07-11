"""Funnel instrumentation (PRD §13): key product events are recorded across the
modules and rolled up by the admin funnel endpoint. No child PII in events."""

import uuid

from fastapi.testclient import TestClient


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _funnel(client: TestClient, admin: str, days: int = 30) -> dict[str, int]:
    resp = client.get("/api/v1/analytics/funnel", headers=_auth(admin), params={"days": days})
    assert resp.status_code == 200, resp.text
    return {s["event_type"]: s["count"] for s in resp.json()["stages"]}


def test_funnel_captures_the_journey(client: TestClient, make_admin) -> None:
    admin = make_admin()
    owner, guardian = _signup(client), _signup(client)

    # provider_signup (org create) + listing_published (publish)
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
            "starts_at": "2026-12-01T09:00:00Z",
            "ends_at": "2026-12-01T15:00:00Z",
            "capacity": 1,  # single seat → session_filled on hold
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))

    # search_performed + listing_viewed
    client.get("/api/v1/search/sessions", params={"suburb": "Perth"})
    client.get(f"/api/v1/catalog/sessions/{session_id}")

    # session_filled (hold takes the only seat) + checkout_started + checkout_completed
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children",
        headers=_auth(guardian),
        json={"first_name": "Robin", "date_of_birth": "2018-06-01"},
    ).json()["id"]
    payment_id = client.post(
        "/api/v1/booking/checkout",
        headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()["payment_id"]
    client.post(f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian))

    funnel = _funnel(client, admin)
    for event_type in [
        "provider_signup",
        "listing_published",
        "search_performed",
        "listing_viewed",
        "session_filled",
        "checkout_started",
        "checkout_completed",
    ]:
        assert funnel.get(event_type, 0) >= 1, f"missing {event_type}: {funnel}"
    # Every taxonomy stage is present (0 allowed), including the unexercised one.
    assert "booking_cancelled" in funnel


def test_booking_cancelled_event(client: TestClient, make_admin) -> None:
    admin = make_admin()
    owner, guardian = _signup(client), _signup(client)
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
            "starts_at": "2026-12-01T09:00:00Z",
            "ends_at": "2026-12-01T15:00:00Z",
            "capacity": 5,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children",
        headers=_auth(guardian),
        json={"first_name": "Robin", "date_of_birth": "2018-06-01"},
    ).json()["id"]
    payment_id = client.post(
        "/api/v1/booking/checkout",
        headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()["payment_id"]
    client.post(f"/api/v1/booking/payments/{payment_id}/cancel", headers=_auth(guardian))

    assert _funnel(client, admin)["booking_cancelled"] >= 1


def test_funnel_requires_admin(client: TestClient) -> None:
    guardian = _signup(client)
    assert client.get("/api/v1/analytics/funnel", headers=_auth(guardian)).status_code == 403
