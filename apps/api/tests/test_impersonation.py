"""Impersonation (PRD §10.3): view-as is read-only, act-as can mutate and is
audited with the true actor, the token can't escalate to admin, and ending a
session revokes it immediately."""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> tuple[str, str]:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    token = client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]
    user_id = client.get("/api/v1/identity/me", headers=_auth(token)).json()["id"]
    return token, user_id


def _impersonate(client: TestClient, admin: str, target_id: str, mode: str) -> dict:
    resp = client.post(
        "/api/v1/admin/impersonations",
        headers=_auth(admin),
        json={"target_user_id": target_id, "mode": mode, "reason": "support"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_view_as_is_readonly_and_shows_target(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    _, target_id = _signup(client)
    token = _impersonate(client, admin, target_id, "view_as")["token"]

    # A GET renders the target's identity.
    me = client.get("/api/v1/identity/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["id"] == target_id

    # A mutation is refused — read-only session.
    blocked = client.post(
        "/api/v1/identity/children",
        headers=_auth(token),
        json={"first_name": "Nope", "date_of_birth": "2018-01-01"},
    )
    assert blocked.status_code == 403


def test_act_as_can_mutate_and_is_audited(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    target_token, target_id = _signup(client)
    imp_token = _impersonate(client, admin, target_id, "act_as")["token"]

    # Act on the target's behalf: add a child to THEIR account.
    created = client.post(
        "/api/v1/identity/children",
        headers=_auth(imp_token),
        json={"first_name": "Sam", "date_of_birth": "2018-01-01"},
    )
    assert created.status_code == 201

    # The child belongs to the target (visible via the target's own token).
    theirs = client.get("/api/v1/identity/children", headers=_auth(target_token)).json()
    assert [c["first_name"] for c in theirs] == ["Sam"]

    # The action is in the audit trail with the admin as the true actor.
    audit = client.get(
        "/api/v1/audit", headers=_auth(admin), params={"entity_type": "http"}
    ).json()
    assert any(e["impersonated_id"] == target_id for e in audit)


def test_impersonation_cannot_reach_admin_routes(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    _, target_id = _signup(client)
    token = _impersonate(client, admin, target_id, "act_as")["token"]
    # The impersonation token has adm=False → admin routes are forbidden.
    assert client.get("/api/v1/admin/orgs", headers=_auth(token)).status_code == 403


def test_cannot_impersonate_admin_or_self(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    admin_id = client.get("/api/v1/identity/me", headers=_auth(admin)).json()["id"]
    other_admin = make_admin()
    other_admin_id = client.get("/api/v1/identity/me", headers=_auth(other_admin)).json()["id"]

    # Self.
    resp_self = client.post(
        "/api/v1/admin/impersonations",
        headers=_auth(admin),
        json={"target_user_id": admin_id, "mode": "view_as"},
    )
    assert resp_self.status_code == 400
    # Another admin.
    resp_admin = client.post(
        "/api/v1/admin/impersonations",
        headers=_auth(admin),
        json={"target_user_id": other_admin_id, "mode": "view_as"},
    )
    assert resp_admin.status_code == 400


def test_ending_session_revokes_the_token(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    _, target_id = _signup(client)
    result = _impersonate(client, admin, target_id, "view_as")
    token, session_id = result["token"], result["session_id"]

    # Works before ending.
    assert client.get("/api/v1/identity/me", headers=_auth(token)).status_code == 200

    ended = client.post(f"/api/v1/admin/impersonations/{session_id}/end", headers=_auth(admin))
    assert ended.status_code == 204

    # Immediately revoked.
    assert client.get("/api/v1/identity/me", headers=_auth(token)).status_code == 401


def test_impersonation_requires_admin(client: TestClient) -> None:
    user_token, _ = _signup(client)
    _, target_id = _signup(client)
    resp = client.post(
        "/api/v1/admin/impersonations",
        headers=_auth(user_token),
        json={"target_user_id": target_id, "mode": "view_as"},
    )
    assert resp.status_code == 403
