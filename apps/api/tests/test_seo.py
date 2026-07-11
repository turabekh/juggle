"""SEO sitemap (PRD §7.1): every indexable listing (published, upcoming,
not cancelled) appears in /catalog/sitemap.xml; others don't."""

import uuid

from fastapi.testclient import TestClient

FUTURE = ("2030-09-30T09:00:00Z", "2030-09-30T15:00:00Z")
PAST = ("2020-01-11T09:00:00Z", "2020-01-11T15:00:00Z")


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _session(client: TestClient, owner: str, *, publish: bool, starts, ends) -> str:
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
            "starts_at": starts,
            "ends_at": ends,
            "capacity": 5,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    if publish:
        client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return session_id


def test_sitemap_lists_only_indexable_sessions(client: TestClient) -> None:
    owner = _signup(client)
    published = _session(client, owner, publish=True, starts=FUTURE[0], ends=FUTURE[1])
    unpublished = _session(client, owner, publish=False, starts=FUTURE[0], ends=FUTURE[1])
    past = _session(client, owner, publish=True, starts=PAST[0], ends=PAST[1])

    resp = client.get("/api/v1/catalog/sitemap.xml")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    body = resp.text
    assert f"/sessions/{published}" in body
    assert f"/sessions/{unpublished}" not in body  # draft not indexable
    assert f"/sessions/{past}" not in body  # past not indexable
    assert body.startswith("<?xml")
    assert "<urlset" in body
