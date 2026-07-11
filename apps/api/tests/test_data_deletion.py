"""Data-deletion / APP compliance (PRD §10.2): a guardian (or admin) can delete
an account, irreversibly stripping the guardian's and their children's PII while
keeping the rows that bookings/payments reference."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _signup(client: TestClient) -> tuple[str, str]:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    token = client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]
    return email, token


def _add_child(client: TestClient, token: str) -> str:
    return client.post(
        "/api/v1/identity/children",
        headers=_auth(token),
        json={
            "first_name": "Robin",
            "date_of_birth": "2018-06-01",
            "medical_notes": "peanut allergy",
            "emergency_contact_name": "Gran",
            "emergency_contact_phone": "0400000000",
        },
    ).json()["id"]


def test_self_service_deletion_strips_pii(client: TestClient, db: Session) -> None:
    from juggle.modules.identity.core.models import Child, UserAccount, UserStatus

    email, token = _signup(client)
    child_id = _add_child(client, token)

    resp = client.delete("/api/v1/identity/me", headers=_auth(token))
    assert resp.status_code == 204

    user = db.scalar(select(UserAccount).where(UserAccount.email == email))
    assert user is None  # email was rewritten
    deleted = db.get(UserAccount, uuid.UUID(_jwt_sub(token)))
    assert deleted is not None
    assert deleted.status is UserStatus.deleted
    assert deleted.email.endswith("@removed.invalid")
    assert deleted.full_name is None
    assert deleted.password_hash is None

    child = db.get(Child, uuid.UUID(child_id))
    assert child is not None  # row kept (bookings may reference it)
    assert child.first_name == "Removed"
    assert child.medical_notes is None
    assert child.emergency_contact_name is None


def test_deleted_user_cannot_log_in(client: TestClient) -> None:
    email, token = _signup(client)
    client.delete("/api/v1/identity/me", headers=_auth(token))
    resp = client.post(
        "/api/v1/identity/login", json={"email": email, "password": "supersecret"}
    )
    assert resp.status_code == 401


def test_admin_deletes_user_and_sees_bookings(client: TestClient, make_admin) -> None:
    admin = make_admin()
    email, token = _signup(client)
    _add_child(client, token)

    # Admin support: booking history endpoint works (empty here).
    hist = client.get(f"/api/v1/admin/users/{_jwt_sub(token)}/bookings", headers=_auth(admin))
    assert hist.status_code == 200
    assert hist.json() == []

    resp = client.post(f"/api/v1/admin/users/{_jwt_sub(token)}/delete", headers=_auth(admin))
    assert resp.status_code == 204
    # Now they can't log in.
    assert (
        client.post(
            "/api/v1/identity/login", json={"email": email, "password": "supersecret"}
        ).status_code
        == 401
    )


def test_admin_cannot_delete_admin(client: TestClient, make_admin, db: Session) -> None:
    from juggle.modules.identity.core.models import UserAccount

    admin = make_admin()
    _email, victim = _signup(client)
    # Promote the victim to admin.
    victim_user = db.get(UserAccount, uuid.UUID(_jwt_sub(victim)))
    assert victim_user is not None
    victim_user.is_admin = True
    db.flush()

    resp = client.post(
        f"/api/v1/admin/users/{victim_user.id}/delete", headers=_auth(admin)
    )
    assert resp.status_code == 409


def _jwt_sub(token: str) -> str:
    import base64
    import json

    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["sub"]
