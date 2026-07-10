"""Catalog endpoints: providers build venues/programs/sessions, publishing
gates public visibility, and non-members are locked out."""

import uuid

from fastapi.testclient import TestClient

_SESSION_BODY = {
    "starts_at": "2026-09-30T09:00:00Z",
    "ends_at": "2026-09-30T15:00:00Z",
    "capacity": 12,
    "price_cents": 5500,
    "age_min": 5,
    "age_max": 12,
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _make_org(client: TestClient, token: str, name: str = "Kids Co") -> str:
    return client.post("/api/v1/org", headers=_auth(token), json={"name": name}).json()["id"]


def test_provider_can_build_and_publish_a_program(client: TestClient) -> None:
    token = _signup(client)
    org_id = _make_org(client, token)

    venue = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(token),
        json={
            "organisation_id": org_id,
            "name": "Community Hall",
            "suburb": "Perth",
            "postcode": "6000",
            "latitude": -31.95,
            "longitude": 115.86,
        },
    )
    assert venue.status_code == 201, venue.text
    venue_id = venue.json()["id"]

    program = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(token),
        json={"organisation_id": org_id, "title": "Art Camp", "category": "art"},
    )
    assert program.status_code == 201
    assert program.json()["status"] == "draft"
    program_id = program.json()["id"]

    session = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(token),
        json={"venue_id": venue_id, **_SESSION_BODY},
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["id"]
    assert session.json()["seats_remaining"] == 12

    # Not visible publicly until the program is published.
    assert client.get(f"/api/v1/catalog/sessions/{session_id}").status_code == 404

    published = client.post(
        f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(token)
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    public = client.get(f"/api/v1/catalog/sessions/{session_id}")
    assert public.status_code == 200
    assert public.json()["seats_remaining"] == 12


def test_non_member_cannot_create_program(client: TestClient) -> None:
    owner = _signup(client)
    org_id = _make_org(client, owner)
    outsider = _signup(client)
    resp = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(outsider),
        json={"organisation_id": org_id, "title": "Sneaky", "category": "art"},
    )
    assert resp.status_code == 403


def test_session_rejects_a_venue_from_another_org(client: TestClient) -> None:
    token = _signup(client)
    org1 = _make_org(client, token, "Org One")
    org2 = _make_org(client, token, "Org Two")
    venue2 = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(token),
        json={"organisation_id": org2, "name": "Other Hall"},
    ).json()["id"]
    program1 = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(token),
        json={"organisation_id": org1, "title": "Prog", "category": "art"},
    ).json()["id"]

    resp = client.post(
        f"/api/v1/catalog/programs/{program1}/sessions",
        headers=_auth(token),
        json={"venue_id": venue2, **_SESSION_BODY},
    )
    assert resp.status_code == 400


def test_session_with_end_before_start_is_rejected(client: TestClient) -> None:
    token = _signup(client)
    org_id = _make_org(client, token)
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(token),
        json={"organisation_id": org_id, "name": "Hall"},
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(token),
        json={"organisation_id": org_id, "title": "Prog", "category": "art"},
    ).json()["id"]

    resp = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(token),
        json={
            "venue_id": venue_id,
            "starts_at": "2026-09-30T15:00:00Z",
            "ends_at": "2026-09-30T09:00:00Z",
            "capacity": 10,
            "price_cents": 100,
            "age_min": 5,
            "age_max": 10,
        },
    )
    assert resp.status_code == 422  # caught by the schema validator
