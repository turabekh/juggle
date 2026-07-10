"""Org endpoints: create an organisation (creator becomes owner) and manage
members with role-based authorisation."""

import uuid

from fastapi.testclient import TestClient


def _signup(client: TestClient) -> tuple[str, uuid.UUID]:
    email = f"prov-{uuid.uuid4().hex[:8]}@example.com"
    token = client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]
    user_id = uuid.UUID(client.get("/api/v1/identity/me", headers=_auth(token)).json()["id"])
    return token, user_id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_org_makes_creator_the_owner(client: TestClient) -> None:
    owner_token, owner_id = _signup(client)
    resp = client.post(
        "/api/v1/org", headers=_auth(owner_token), json={"name": "Bright Sparks STEM"}
    )
    assert resp.status_code == 201, resp.text
    org = resp.json()
    assert org["slug"].startswith("bright-sparks-stem-")
    assert org["status"] == "pending"

    members = client.get(
        f"/api/v1/org/{org['id']}/members", headers=_auth(owner_token)
    ).json()
    assert len(members) == 1
    assert members[0]["role"] == "owner"
    assert members[0]["user_account_id"] == str(owner_id)


def test_owner_can_add_staff_but_non_member_cannot(client: TestClient) -> None:
    owner_token, _ = _signup(client)
    staff_token, staff_id = _signup(client)
    outsider_token, _ = _signup(client)

    org_id = client.post(
        "/api/v1/org", headers=_auth(owner_token), json={"name": "Acme Sports"}
    ).json()["id"]

    # Owner adds staff.
    added = client.post(
        f"/api/v1/org/{org_id}/members",
        headers=_auth(owner_token),
        json={"user_account_id": str(staff_id), "role": "staff"},
    )
    assert added.status_code == 201, added.text
    assert added.json()["role"] == "staff"

    # Adding the same user again conflicts.
    dup = client.post(
        f"/api/v1/org/{org_id}/members",
        headers=_auth(owner_token),
        json={"user_account_id": str(staff_id), "role": "staff"},
    )
    assert dup.status_code == 409

    # Newly-added staff is only a member, not an owner: cannot add members.
    forbidden = client.post(
        f"/api/v1/org/{org_id}/members",
        headers=_auth(staff_token),
        json={"user_account_id": str(uuid.uuid4()), "role": "staff"},
    )
    assert forbidden.status_code == 403

    # An outsider cannot even list members.
    assert (
        client.get(f"/api/v1/org/{org_id}/members", headers=_auth(outsider_token)).status_code
        == 403
    )


def test_adding_unknown_user_is_rejected(client: TestClient) -> None:
    owner_token, _ = _signup(client)
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner_token), json={"name": "Ghost Org"}
    ).json()["id"]
    resp = client.post(
        f"/api/v1/org/{org_id}/members",
        headers=_auth(owner_token),
        json={"user_account_id": str(uuid.uuid4()), "role": "staff"},
    )
    assert resp.status_code == 400
