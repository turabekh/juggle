"""Feature flags: off by default, admin-managed, with rollout + targeting."""

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


def _evaluate(client: TestClient, token: str, key: str) -> bool:
    return client.get(f"/api/v1/flags/{key}/enabled", headers=_auth(token)).json()["enabled"]


def test_unknown_flag_is_off(client: TestClient) -> None:
    token, _ = _signup(client)
    assert _evaluate(client, token, "nonexistent") is False


def test_admin_enable_full_rollout(client: TestClient, make_admin: Callable[[], str]) -> None:
    admin = make_admin()
    token, _ = _signup(client)
    resp = client.put(
        "/api/v1/flags/new_checkout",
        headers=_auth(admin),
        json={"enabled": True, "rollout_percentage": 100},
    )
    assert resp.status_code == 200
    assert _evaluate(client, token, "new_checkout") is True


def test_disabled_flag_is_off_even_at_100(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    token, _ = _signup(client)
    client.put(
        "/api/v1/flags/paused",
        headers=_auth(admin),
        json={"enabled": False, "rollout_percentage": 100},
    )
    assert _evaluate(client, token, "paused") is False


def test_targeting_specific_user(client: TestClient, make_admin: Callable[[], str]) -> None:
    admin = make_admin()
    target_token, target_id = _signup(client)
    other_token, _ = _signup(client)
    client.put(
        "/api/v1/flags/beta",
        headers=_auth(admin),
        json={"enabled": True, "rollout_percentage": 0, "targeting": {"user_ids": [target_id]}},
    )
    assert _evaluate(client, target_token, "beta") is True
    assert _evaluate(client, other_token, "beta") is False


def test_flag_management_requires_admin(client: TestClient) -> None:
    token, _ = _signup(client)
    assert client.get("/api/v1/flags", headers=_auth(token)).status_code == 403
    assert (
        client.put(
            "/api/v1/flags/x", headers=_auth(token), json={"enabled": True}
        ).status_code
        == 403
    )
