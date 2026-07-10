"""New provider/admin support endpoints: list-my-orgs, list-org-programs, and
admin user search."""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient, email: str | None = None) -> str:
    email = email or f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def test_list_my_orgs_only_shows_membership(client: TestClient) -> None:
    owner = _signup(client)
    outsider = _signup(client)
    org = client.post("/api/v1/org", headers=_auth(owner), json={"name": "My Co"}).json()

    mine = client.get("/api/v1/org", headers=_auth(owner))
    assert mine.status_code == 200
    assert [o["id"] for o in mine.json()] == [org["id"]]

    # A different user sees none of it.
    assert client.get("/api/v1/org", headers=_auth(outsider)).json() == []


def test_list_org_programs_member_gated(client: TestClient) -> None:
    owner = _signup(client)
    outsider = _signup(client)
    org_id = client.post("/api/v1/org", headers=_auth(owner), json={"name": "Prog Co"}).json()["id"]
    client.post(
        "/api/v1/catalog/programs",
        headers=_auth(owner),
        json={"organisation_id": org_id, "title": "Camp A", "category": "art"},
    )
    client.post(
        "/api/v1/catalog/programs",
        headers=_auth(owner),
        json={"organisation_id": org_id, "title": "Camp B", "category": "sport"},
    )

    listed = client.get(
        "/api/v1/catalog/programs", headers=_auth(owner), params={"organisation_id": org_id}
    )
    assert listed.status_code == 200
    assert {p["title"] for p in listed.json()} == {"Camp A", "Camp B"}

    # Non-member is forbidden.
    forbidden = client.get(
        "/api/v1/catalog/programs", headers=_auth(outsider), params={"organisation_id": org_id}
    )
    assert forbidden.status_code == 403


def test_admin_user_search(client: TestClient, make_admin: Callable[[], str]) -> None:
    admin = make_admin()
    unique = uuid.uuid4().hex[:8]
    _signup(client, email=f"needle-{unique}@example.com")

    found = client.get(
        "/api/v1/admin/users", headers=_auth(admin), params={"q": f"needle-{unique}"}
    )
    assert found.status_code == 200
    rows = found.json()
    assert len(rows) == 1
    assert rows[0]["email"] == f"needle-{unique}@example.com"


def test_user_search_requires_admin(client: TestClient) -> None:
    user = _signup(client)
    resp = client.get("/api/v1/admin/users", headers=_auth(user), params={"q": "x"})
    assert resp.status_code == 403
