"""Duplicate-account merge (PRD §10.2): consolidate a parent's two logins — their
children, bookings and waitlist move to the primary; the duplicate is deactivated."""

import uuid

from fastapi.testclient import TestClient


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _signup(client: TestClient) -> tuple[str, str]:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    token = client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]
    return email, token


def _sub(token: str) -> str:
    import base64
    import json

    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))["sub"]


def _session(client: TestClient, owner: str, *, capacity: int = 5) -> str:
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
            "starts_at": "2030-09-30T09:00:00Z",
            "ends_at": "2030-09-30T15:00:00Z",
            "capacity": capacity,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return session_id


def _book_confirm(client: TestClient, token: str, session_id: str) -> None:
    hold = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(token),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child = client.post(
        "/api/v1/identity/children",
        headers=_auth(token),
        json={"first_name": "Robin", "date_of_birth": "2019-06-01"},
    ).json()["id"]
    pid = client.post(
        "/api/v1/booking/checkout",
        headers=_auth(token),
        json={
            "idempotency_key": f"k-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold, "children": [{"child_id": child}]}],
        },
    ).json()["payment_id"]
    client.post(f"/api/v1/booking/payments/{pid}/confirm", headers=_auth(token))


def _merge(client: TestClient, admin: str, source: str, target: str):
    return client.post(
        "/api/v1/admin/users/merge",
        headers=_auth(admin),
        json={"source_id": source, "target_id": target},
    )


def test_merge_moves_children_and_bookings(client: TestClient, make_admin) -> None:
    admin = make_admin()
    _owner_email, owner = _signup(client)
    src_email, source = _signup(client)
    _tgt_email, target = _signup(client)
    session_id = _session(client, owner)
    _book_confirm(client, source, session_id)  # source has a child + a booking

    resp = _merge(client, admin, _sub(source), _sub(target))
    assert resp.status_code == 204, resp.text

    # Target now owns the child and the booking.
    assert len(client.get("/api/v1/identity/children", headers=_auth(target)).json()) == 1
    assert len(client.get("/api/v1/booking/bookings", headers=_auth(target)).json()) == 1
    # The duplicate can no longer log in.
    assert (
        client.post(
            "/api/v1/identity/login", json={"email": src_email, "password": "supersecret"}
        ).status_code
        == 401
    )


def test_waitlist_conflict_is_resolved(client: TestClient, make_admin) -> None:
    admin = make_admin()
    _owner_email, owner = _signup(client)
    _s, source = _signup(client)
    _t, target = _signup(client)
    session_id = _session(client, owner, capacity=1)
    # Fill the only seat so the session is sold out.
    _holder_e, holder = _signup(client)
    _book_confirm(client, holder, session_id)

    # Both source and target join the same session's waitlist (both active).
    client.post("/api/v1/waitlist", headers=_auth(source), json={"session_id": session_id})
    client.post("/api/v1/waitlist", headers=_auth(target), json={"session_id": session_id})

    assert _merge(client, admin, _sub(source), _sub(target)).status_code == 204

    # Target keeps exactly one active entry (the source's duplicate was dropped).
    mine = client.get("/api/v1/waitlist/mine", headers=_auth(target)).json()
    on_session = [e for e in mine if e["session_id"] == session_id]
    assert len(on_session) == 1


def test_merge_guards(client: TestClient, make_admin) -> None:
    admin = make_admin()
    _e, a = _signup(client)
    _e2, b = _signup(client)
    # Same account → 409.
    assert _merge(client, admin, _sub(a), _sub(a)).status_code == 409
    # Unknown target → 404.
    assert _merge(client, admin, _sub(a), str(uuid.uuid4())).status_code == 404
    # Merging the admin → 409.
    assert _merge(client, admin, _sub(a), _sub(admin)).status_code == 409
