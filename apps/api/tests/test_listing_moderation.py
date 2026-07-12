"""Listing moderation guardrail (ADR-0006 / EXT-1 §2-E2): an admin can reject a listing —
notably a recurring/term-enrolment class disguised as a one-off — which unpublishes it."""

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


def _publish(client: TestClient, owner: str) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues", headers=_auth(owner),
        json={"organisation_id": org_id, "name": "Hall", "latitude": -31.95, "longitude": 115.86},
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs", headers=_auth(owner),
        json={"organisation_id": org_id, "title": "Weekly Term Class", "category": "art"},
    ).json()["id"]
    client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions", headers=_auth(owner),
        json={"venue_id": venue_id, "starts_at": "2026-10-03T02:00:00Z",
              "ends_at": "2026-10-03T04:00:00Z", "capacity": 5, "price_cents": 5000,
              "age_min": 4, "age_max": 12},
    )
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return program_id, org_id


def _searchable(client: TestClient, program_id: str) -> bool:
    items = client.get(
        "/api/v1/search/sessions", params={"lat": -31.95, "lng": 115.86, "radius_km": 25}
    ).json()["items"]
    return any(c["program_id"] == program_id for c in items)


def test_admin_rejects_recurring_enrolment_listing(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    owner, admin = _signup(client), make_admin()
    program_id, _org = _publish(client, owner)
    assert _searchable(client, program_id)

    resp = client.post(
        f"/api/v1/admin/listings/{program_id}/reject", headers=_auth(admin),
        json={"reason": "recurring_enrolment", "note": "term class disguised as a one-off"},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "program_id": program_id, "status": "unpublished", "reason": "recurring_enrolment",
    }
    assert not _searchable(client, program_id)  # pulled from discovery


def test_reject_requires_admin(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    program_id, _org = _publish(client, owner)
    resp = client.post(
        f"/api/v1/admin/listings/{program_id}/reject", headers=_auth(outsider),
        json={"reason": "recurring_enrolment"},
    )
    assert resp.status_code in (401, 403)


def test_reject_unknown_listing_404(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    resp = client.post(
        f"/api/v1/admin/listings/{uuid.uuid4()}/reject", headers=_auth(admin),
        json={"reason": "other"},
    )
    assert resp.status_code == 404


def test_reject_validates_reason(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    owner, admin = _signup(client), make_admin()
    program_id, _org = _publish(client, owner)
    resp = client.post(
        f"/api/v1/admin/listings/{program_id}/reject", headers=_auth(admin),
        json={"reason": "made_up_reason"},
    )
    assert resp.status_code == 422  # not in the allowed reason set
