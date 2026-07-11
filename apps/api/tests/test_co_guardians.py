"""Multiple guardians per family (PRD §7.3): a guardian invites a co-guardian;
once accepted, they share children and see each other's bookings."""

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


def _add_child(client: TestClient, token: str, name: str) -> str:
    return client.post(
        "/api/v1/identity/children",
        headers=_auth(token),
        json={"first_name": name, "date_of_birth": "2018-06-01"},
    ).json()["id"]


def _session(client: TestClient, owner: str) -> str:
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
            "starts_at": "2026-12-01T09:00:00Z",
            "ends_at": "2026-12-01T15:00:00Z",
            "capacity": 5,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return session_id


def _link(client: TestClient, a_token: str, b_email: str, b_token: str) -> str:
    """A invites B; B accepts. Returns the link id."""
    invite = client.post(
        "/api/v1/identity/co-guardians", headers=_auth(a_token), json={"email": b_email}
    )
    assert invite.status_code == 201, invite.text
    link_id = invite.json()["id"]
    # B sees a received, not-yet-accepted invite.
    received = client.get("/api/v1/identity/co-guardians", headers=_auth(b_token)).json()
    assert received[0]["direction"] == "received"
    assert received[0]["accepted"] is False
    accept = client.post(
        f"/api/v1/identity/co-guardians/{link_id}/accept", headers=_auth(b_token)
    )
    assert accept.status_code == 200
    assert accept.json()["accepted"] is True
    return link_id


def test_accepted_co_guardian_shares_children(client: TestClient) -> None:
    a_email, a = _signup(client)
    b_email, b = _signup(client)
    _add_child(client, a, "Ada")
    _add_child(client, b, "Bo")

    # Before linking: each sees only their own child.
    assert len(client.get("/api/v1/identity/children", headers=_auth(a)).json()) == 1

    _link(client, a, b_email, b)

    # After: both see both children.
    def kid_names(token: str) -> set[str]:
        rows = client.get("/api/v1/identity/children", headers=_auth(token)).json()
        return {c["first_name"] for c in rows}

    assert kid_names(a) == {"Ada", "Bo"}
    assert kid_names(b) == {"Ada", "Bo"}


def test_pending_invite_does_not_share(client: TestClient) -> None:
    a_email, a = _signup(client)
    b_email, b = _signup(client)
    _add_child(client, a, "Ada")
    # Invite but do NOT accept.
    client.post("/api/v1/identity/co-guardians", headers=_auth(a), json={"email": b_email})
    assert client.get("/api/v1/identity/children", headers=_auth(b)).json() == []


def test_co_guardian_can_book_shared_child_and_both_see_it(client: TestClient) -> None:
    a_email, a = _signup(client)
    b_email, b = _signup(client)
    _owner_email, owner = _signup(client)  # provider
    session_id = _session(client, owner)
    child_id = _add_child(client, a, "Ada")  # A's child
    _link(client, a, b_email, b)

    # B (co-guardian) books A's child.
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(b),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    order = client.post(
        "/api/v1/booking/checkout",
        headers=_auth(b),
        json={
            "idempotency_key": f"k-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    )
    assert order.status_code == 201, order.text

    # Both A and B see the booking.
    assert len(client.get("/api/v1/booking/bookings", headers=_auth(a)).json()) == 1
    assert len(client.get("/api/v1/booking/bookings", headers=_auth(b)).json()) == 1


def test_invite_unknown_email_404(client: TestClient) -> None:
    _e, a = _signup(client)
    resp = client.post(
        "/api/v1/identity/co-guardians",
        headers=_auth(a),
        json={"email": "nobody@example.com"},
    )
    assert resp.status_code == 404


def test_cannot_invite_self(client: TestClient) -> None:
    email, a = _signup(client)
    resp = client.post(
        "/api/v1/identity/co-guardians", headers=_auth(a), json={"email": email}
    )
    assert resp.status_code == 409


def test_remove_link_revokes_sharing(client: TestClient) -> None:
    a_email, a = _signup(client)
    b_email, b = _signup(client)
    _add_child(client, a, "Ada")
    link_id = _link(client, a, b_email, b)

    assert len(client.get("/api/v1/identity/children", headers=_auth(b)).json()) == 1
    assert (
        client.delete(f"/api/v1/identity/co-guardians/{link_id}", headers=_auth(b)).status_code
        == 204
    )
    assert client.get("/api/v1/identity/children", headers=_auth(b)).json() == []
