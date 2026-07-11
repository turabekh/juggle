"""Analytics (PRD §8.6): provider fill rate, revenue, and new-vs-returning
families rolled up from catalog + booking. Org-member gated."""

import uuid

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org(client: TestClient, owner: str) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(owner),
        json={"organisation_id": org_id, "name": "Hall"},
    ).json()["id"]
    return org_id, venue_id


def _session(
    client: TestClient, owner: str, org_id: str, venue_id: str, *, capacity=5, price=5000
) -> tuple[str, str]:
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(owner),
        json={"organisation_id": org_id, "title": f"P {uuid.uuid4().hex[:4]}", "category": "art"},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(owner),
        json={
            "venue_id": venue_id,
            "starts_at": "2026-12-01T09:00:00Z",
            "ends_at": "2026-12-01T15:00:00Z",
            "capacity": capacity,
            "price_cents": price,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return program_id, session_id


def _book_confirm(client: TestClient, guardian: str, session_id: str) -> None:
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
    pid = client.post(
        "/api/v1/booking/checkout",
        headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()["payment_id"]
    client.post(f"/api/v1/booking/payments/{pid}/confirm", headers=_auth(guardian))


def _analytics(client: TestClient, token: str, org_id: str):
    return client.get(f"/api/v1/analytics/organisations/{org_id}", headers=_auth(token))


def test_fill_rate_revenue_and_family_mix(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org(client, owner)
    _, s1 = _session(client, owner, org_id, venue_id, capacity=4, price=5000)
    _, s2 = _session(client, owner, org_id, venue_id, capacity=2, price=3000)

    returning = _signup(client)  # books both sessions → returning family
    new_family = _signup(client)  # books one → new family
    _book_confirm(client, returning, s1)
    _book_confirm(client, returning, s2)
    _book_confirm(client, new_family, s1)

    data = _analytics(client, owner, org_id).json()
    # 2 seats taken on s1 (cap 4) + 1 on s2 (cap 2) = 3 booked / 6 capacity.
    assert data["capacity_total"] == 6
    assert data["booked_total"] == 3
    assert data["fill_rate"] == 0.5
    # Revenue: s1 two bookings * 5000 + s2 one * 3000 = 13000.
    assert data["revenue_cents"] == 13000
    assert data["bookings"] == 3
    assert data["families"] == {"total": 2, "new": 1, "returning": 1}
    assert len(data["programs"]) == 2


def test_empty_org_is_zeroed(client: TestClient) -> None:
    owner = _signup(client)
    org_id, _ = _org(client, owner)
    data = _analytics(client, owner, org_id).json()
    assert data["revenue_cents"] == 0
    assert data["fill_rate"] == 0.0
    assert data["families"] == {"total": 0, "new": 0, "returning": 0}


def test_non_member_forbidden(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    org_id, _ = _org(client, owner)
    assert _analytics(client, outsider, org_id).status_code == 403
