"""Identity endpoints: signup → login → me, child profiles, and auth guards."""

import uuid

from fastapi.testclient import TestClient


def _signup(client: TestClient, email: str | None = None) -> str:
    email = email or f"parent-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/identity/signup",
        json={"email": email, "password": "supersecret", "full_name": "Pat Parent"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_signup_returns_usable_token(client: TestClient) -> None:
    token = _signup(client)
    me = client.get("/api/v1/identity/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["email"].endswith("@example.com")
    assert me.json()["is_admin"] is False


def test_duplicate_email_conflicts(client: TestClient) -> None:
    email = f"dupe-{uuid.uuid4().hex[:8]}@example.com"
    _signup(client, email)
    resp = client.post(
        "/api/v1/identity/signup",
        json={"email": email, "password": "supersecret"},
    )
    assert resp.status_code == 409


def test_login_flow_and_bad_password(client: TestClient) -> None:
    email = f"login-{uuid.uuid4().hex[:8]}@example.com"
    _signup(client, email)
    ok = client.post(
        "/api/v1/identity/login", json={"email": email, "password": "supersecret"}
    )
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = client.post(
        "/api/v1/identity/login", json={"email": email, "password": "wrong"}
    )
    assert bad.status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/identity/me").status_code == 401  # no bearer
    bad = client.get("/api/v1/identity/me", headers=_auth("not-a-real-token"))
    assert bad.status_code == 401  # malformed token


def test_children_are_scoped_to_the_guardian(client: TestClient) -> None:
    token_a = _signup(client)
    token_b = _signup(client)
    created = client.post(
        "/api/v1/identity/children",
        headers=_auth(token_a),
        json={"first_name": "Sam", "date_of_birth": "2018-05-01", "photo_consent": True},
    )
    assert created.status_code == 201, created.text
    assert created.json()["first_name"] == "Sam"

    mine = client.get("/api/v1/identity/children", headers=_auth(token_a))
    assert [c["first_name"] for c in mine.json()] == ["Sam"]

    # A different guardian sees none of guardian A's children.
    theirs = client.get("/api/v1/identity/children", headers=_auth(token_b))
    assert theirs.json() == []
