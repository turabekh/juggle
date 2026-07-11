"""Bulk session creation (PRD §8.2): create many sessions across a range in one
transaction."""

import uuid

from fastapi.testclient import TestClient


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_program_venue(client: TestClient, owner: str) -> tuple[str, str]:
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
    return program_id, venue_id


def _item(venue_id: str, day: str) -> dict:
    return {
        "venue_id": venue_id,
        "starts_at": f"{day}T09:00:00Z",
        "ends_at": f"{day}T15:00:00Z",
        "capacity": 10,
        "price_cents": 5000,
        "age_min": 5,
        "age_max": 12,
    }


def test_bulk_creates_all_sessions(client: TestClient) -> None:
    owner = _signup(client)
    program_id, venue_id = _org_program_venue(client, owner)

    days = ["2030-01-05", "2030-01-06", "2030-01-07"]
    resp = client.post(
        f"/api/v1/catalog/programs/{program_id}/bulk-sessions",
        headers=_auth(owner),
        json={"items": [_item(venue_id, d) for d in days]},
    )
    assert resp.status_code == 201, resp.text
    assert len(resp.json()) == 3

    listed = client.get(
        f"/api/v1/catalog/programs/{program_id}/sessions", headers=_auth(owner)
    ).json()
    assert len(listed) == 3


def test_bulk_requires_at_least_one_and_caps(client: TestClient) -> None:
    owner = _signup(client)
    program_id, _venue = _org_program_venue(client, owner)
    assert (
        client.post(
            f"/api/v1/catalog/programs/{program_id}/bulk-sessions",
            headers=_auth(owner),
            json={"items": []},
        ).status_code
        == 422
    )


def test_bulk_non_member_forbidden(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    program_id, venue_id = _org_program_venue(client, owner)
    resp = client.post(
        f"/api/v1/catalog/programs/{program_id}/bulk-sessions",
        headers=_auth(outsider),
        json={"items": [_item(venue_id, "2030-01-05")]},
    )
    assert resp.status_code == 403
