"""Parties supply side (Milestone B1, ADR-0006/PRD §9): a provider's party packages +
capacity-1 slots. Member-gated CRUD; public reads. No money yet (B2–B4)."""

import uuid

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_with_venue(client: TestClient, owner: str) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues", headers=_auth(owner),
        json={"organisation_id": org_id, "name": "Party Hall"},
    ).json()["id"]
    return org_id, venue_id


def _package_body(venue_id: str, **over: object) -> dict[str, object]:
    return {
        "venue_id": venue_id,
        "name": "Superhero Party",
        "per_head_price_cents": 3500,
        "min_headcount": 8,
        "max_headcount": 20,
        "outdoor": False,
        **over,
    }


def test_create_and_list_package(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)

    resp = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id, deposit_pct=30),
    )
    assert resp.status_code == 201, resp.text
    pkg = resp.json()
    assert pkg["name"] == "Superhero Party"
    assert pkg["per_head_price_cents"] == 3500
    assert pkg["deposit_pct"] == 30
    assert pkg["status"] == "active"

    public = client.get(f"/api/v1/parties/orgs/{org_id}/packages").json()
    assert any(p["id"] == pkg["id"] for p in public)


def test_create_package_requires_membership(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    resp = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(outsider),
        json=_package_body(venue_id),
    )
    assert resp.status_code == 403


def test_package_venue_must_belong_to_org(client: TestClient) -> None:
    owner, other = _signup(client), _signup(client)
    org_id, _venue = _org_with_venue(client, owner)
    _other_org, other_venue = _org_with_venue(client, other)  # a venue in a different org
    resp = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(other_venue),
    )
    assert resp.status_code == 404


def test_headcount_band_rejected(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    resp = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id, min_headcount=20, max_headcount=8),
    )
    assert resp.status_code == 400


def test_slots_created_and_publicly_listed(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id),
    ).json()

    resp = client.post(
        f"/api/v1/parties/packages/{pkg['id']}/slots", headers=_auth(owner),
        json={"slots": [
            {"starts_at": "2026-11-07T04:00:00Z", "ends_at": "2026-11-07T06:00:00Z"},
            {"starts_at": "2026-11-08T04:00:00Z", "ends_at": "2026-11-08T06:00:00Z"},
        ]},
    )
    assert resp.status_code == 201
    assert len(resp.json()) == 2

    public = client.get(f"/api/v1/parties/packages/{pkg['id']}/slots").json()
    assert len(public) == 2
    assert all(s["status"] == "available" for s in public)


def test_slot_end_before_start_rejected(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id),
    ).json()
    resp = client.post(
        f"/api/v1/parties/packages/{pkg['id']}/slots", headers=_auth(owner),
        json={"slots": [{"starts_at": "2026-11-07T06:00:00Z", "ends_at": "2026-11-07T04:00:00Z"}]},
    )
    assert resp.status_code == 422


def test_archive_removes_from_public_listing(client: TestClient) -> None:
    owner = _signup(client)
    org_id, venue_id = _org_with_venue(client, owner)
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json=_package_body(venue_id),
    ).json()

    client.post(f"/api/v1/parties/packages/{pkg['id']}/archive", headers=_auth(owner))
    public = client.get(f"/api/v1/parties/orgs/{org_id}/packages").json()
    assert all(p["id"] != pkg["id"] for p in public)
    # But the provider still sees it in the manage view.
    manage = client.get(
        f"/api/v1/parties/orgs/{org_id}/packages/manage", headers=_auth(owner)
    ).json()
    assert any(p["id"] == pkg["id"] and p["status"] == "archived" for p in manage)
