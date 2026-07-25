"""Admin user suspension (PRD §10.2/§10.4).

``UserStatus.suspended`` was already *enforced* everywhere — login, refresh, and a
live status re-check on every request — but nothing could *assign* it, so the
enforcement was unreachable. These cover the assignment path and its guards.
"""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.identity.core import service as identity_service
from juggle.modules.identity.core.models import RefreshToken, UserAccount, UserStatus


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> dict[str, str]:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    body = client.post(
        "/api/v1/identity/signup",
        json={"email": email, "password": "supersecret"},
    ).json()
    body["email"] = email
    return body


def _find_user_id(client: TestClient, admin: str, email: str) -> str:
    rows = client.get(
        "/api/v1/admin/users", headers=_auth(admin), params={"q": email}
    ).json()
    assert len(rows) == 1, rows
    return str(rows[0]["id"])


def test_suspension_kills_the_session_login_and_refresh(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    victim = _signup(client)
    access, refresh = victim["access_token"], victim["refresh_token"]
    assert client.get("/api/v1/identity/me", headers=_auth(access)).status_code == 200

    resp = client.post(
        f"/api/v1/admin/users/{_find_user_id(client, admin, victim['email'])}/suspend",
        headers=_auth(admin),
        json={"reason": "chargeback fraud"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "suspended"

    # 1. the unexpired access token stops working on its very next request,
    assert client.get("/api/v1/identity/me", headers=_auth(access)).status_code == 401
    # 2. the refresh token can't mint a replacement,
    refreshed = client.post("/api/v1/identity/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code == 401
    # 3. and they can't simply log in again.
    login = client.post(
        "/api/v1/identity/login",
        json={"email": victim["email"], "password": "supersecret"},
    )
    assert login.status_code == 401


def test_reinstate_restores_access(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    victim = _signup(client)
    user_id = _find_user_id(client, admin, victim["email"])

    client.post(
        f"/api/v1/admin/users/{user_id}/suspend", headers=_auth(admin), json={}
    )
    resp = client.post(
        f"/api/v1/admin/users/{user_id}/reinstate",
        headers=_auth(admin),
        json={"reason": "resolved"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # Suspension revoked their tokens, so they log in fresh — and it works.
    login = client.post(
        "/api/v1/identity/login",
        json={"email": victim["email"], "password": "supersecret"},
    )
    assert login.status_code == 200
    assert (
        client.get(
            "/api/v1/identity/me", headers=_auth(login.json()["access_token"])
        ).status_code
        == 200
    )


def test_suspension_revokes_every_live_refresh_token(
    client: TestClient, db: Session, make_admin: Callable[[], str]
) -> None:
    """Force-logout is everywhere, not just the session that happened to be current."""
    admin = make_admin()
    victim = _signup(client)
    for _ in range(2):  # extra devices
        client.post(
            "/api/v1/identity/login",
            json={"email": victim["email"], "password": "supersecret"},
        )
    user_id = _find_user_id(client, admin, victim["email"])
    live = select(RefreshToken).where(
        RefreshToken.user_id == uuid.UUID(user_id), RefreshToken.revoked_at.is_(None)
    )
    assert len(list(db.scalars(live))) == 3

    client.post(f"/api/v1/admin/users/{user_id}/suspend", headers=_auth(admin), json={})
    assert list(db.scalars(live)) == []


def test_admin_cannot_suspend_themselves(
    client: TestClient, db: Session, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    me = client.get("/api/v1/identity/me", headers=_auth(admin)).json()
    resp = client.post(
        f"/api/v1/admin/users/{me['id']}/suspend", headers=_auth(admin), json={}
    )
    assert resp.status_code == 409
    user = db.get(UserAccount, uuid.UUID(me["id"]))
    assert user is not None and user.status is UserStatus.active


def test_admin_accounts_cannot_be_suspended(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    """Admins are provisioned at the DB layer; suspending them here would be an
    in-app lockout with no in-app recovery."""
    admin, other_admin = make_admin(), make_admin()
    other = client.get("/api/v1/identity/me", headers=_auth(other_admin)).json()
    resp = client.post(
        f"/api/v1/admin/users/{other['id']}/suspend", headers=_auth(admin), json={}
    )
    assert resp.status_code == 409
    assert client.get("/api/v1/identity/me", headers=_auth(other_admin)).status_code == 200


def test_data_deleted_accounts_cannot_be_suspended_or_reinstated(
    client: TestClient, db: Session, make_admin: Callable[[], str]
) -> None:
    """§10.2 deletion is terminal in both directions — it has already stripped the PII."""
    admin = make_admin()
    victim = _signup(client)
    user_id = _find_user_id(client, admin, victim["email"])
    client.delete("/api/v1/identity/me", headers=_auth(victim["access_token"]))

    for action in ("suspend", "reinstate"):
        resp = client.post(
            f"/api/v1/admin/users/{user_id}/{action}", headers=_auth(admin), json={}
        )
        assert resp.status_code == 409, action
    user = db.get(UserAccount, uuid.UUID(user_id))
    assert user is not None and user.status is UserStatus.deleted


def test_suspension_is_audited_with_the_reason(
    client: TestClient, make_admin: Callable[[], str]
) -> None:
    admin = make_admin()
    victim = _signup(client)
    user_id = _find_user_id(client, admin, victim["email"])
    client.post(
        f"/api/v1/admin/users/{user_id}/suspend",
        headers=_auth(admin),
        json={"reason": "policy breach"},
    )

    trail = client.get(
        "/api/v1/audit",
        headers=_auth(admin),
        params={"entity_type": "user_account", "entity_id": user_id},
    ).json()
    entry = next(e for e in trail if e["action"] == "admin.user.suspend")
    assert entry["detail"]["reason"] == "policy breach"
    assert entry["detail"]["status"] == "suspended"


def test_unknown_user_is_404(client: TestClient, make_admin: Callable[[], str]) -> None:
    admin = make_admin()
    resp = client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/suspend", headers=_auth(admin), json={}
    )
    assert resp.status_code == 404


def test_suspension_requires_admin(client: TestClient) -> None:
    victim, outsider = _signup(client), _signup(client)
    me = client.get("/api/v1/identity/me", headers=_auth(victim["access_token"])).json()
    resp = client.post(
        f"/api/v1/admin/users/{me['id']}/suspend",
        headers=_auth(outsider["access_token"]),
        json={},
    )
    assert resp.status_code == 403


def test_service_refuses_to_route_deletion_through_status(db: Session) -> None:
    """``deleted`` is not assignable here — §10.2 anonymisation must run."""
    try:
        identity_service.set_account_status(
            db, user_id=uuid.uuid4(), status=UserStatus.deleted
        )
    except identity_service.AccountDeleted:
        return
    raise AssertionError("expected AccountDeleted")
