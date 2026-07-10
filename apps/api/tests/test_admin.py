"""Admin ops: provider approval/suspension (with publish gate) and the bookings
console refund."""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org(client: TestClient, token: str) -> str:
    return client.post(
        "/api/v1/org", headers=_auth(token), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]


def _program(client: TestClient, token: str, org_id: str) -> str:
    return client.post(
        "/api/v1/catalog/programs",
        headers=_auth(token),
        json={"organisation_id": org_id, "title": "Camp", "category": "art"},
    ).json()["id"]


def test_admin_can_list_and_approve_pending_orgs(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    provider = _signup(client)
    org_id = _org(client, provider)

    pending = client.get("/api/v1/admin/orgs", headers=_auth(admin), params={"status": "pending"})
    assert pending.status_code == 200
    assert org_id in {o["id"] for o in pending.json()}

    approved = client.post(f"/api/v1/admin/orgs/{org_id}/approve", headers=_auth(admin))
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_suspended_org_cannot_publish(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    provider = _signup(client)
    org_id = _org(client, provider)
    program_id = _program(client, provider, org_id)

    # Publishing works while pending.
    assert (
        client.post(
            f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(provider)
        ).status_code
        == 200
    )

    # After suspension, publishing a (re-drafted) program is blocked.
    client.post(f"/api/v1/admin/orgs/{org_id}/suspend", headers=_auth(admin))
    program2 = _program(client, provider, org_id)
    blocked = client.post(
        f"/api/v1/catalog/programs/{program2}/publish", headers=_auth(provider)
    )
    assert blocked.status_code == 403


def test_admin_endpoints_require_admin(client: TestClient) -> None:
    user = _signup(client)
    assert client.get("/api/v1/admin/orgs", headers=_auth(user)).status_code == 403
    org_id = _org(client, user)
    assert (
        client.post(f"/api/v1/admin/orgs/{org_id}/approve", headers=_auth(user)).status_code == 403
    )


def test_admin_refund_releases_and_refunds(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    provider, guardian = _signup(client), _signup(client)
    org_id = _org(client, provider)
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(provider),
        json={"organisation_id": org_id, "name": "Hall"},
    ).json()["id"]
    program_id = _program(client, provider, org_id)
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(provider),
        json={
            "venue_id": venue_id,
            "starts_at": "2026-09-30T09:00:00Z",
            "ends_at": "2026-09-30T15:00:00Z",
            "capacity": 2,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(provider))

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
    payment_id = order["payment_id"]
    client.post(f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian))
    assert (
        client.get(f"/api/v1/inventory/sessions/{session_id}/availability").json()[
            "seats_remaining"
        ]
        == 1
    )

    refunded = client.post(
        f"/api/v1/admin/payments/{payment_id}/refund",
        headers=_auth(admin),
        json={"reason": "duplicate charge"},
    )
    assert refunded.status_code == 200
    assert refunded.json()["status"] == "refunded"
    assert refunded.json()["bookings"][0]["status"] == "refunded"
    # Seat released.
    assert (
        client.get(f"/api/v1/inventory/sessions/{session_id}/availability").json()[
            "seats_remaining"
        ]
        == 2
    )
