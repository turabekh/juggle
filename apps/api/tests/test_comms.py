"""Comms (PRD §8.5): a provider broadcasts to the families booked on a session.
Org-member gated; delivers via the notification log; records outbound history."""

import uuid

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_and_session(client: TestClient, owner: str) -> tuple[str, str]:
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
    return org_id, session_id


def _book_confirm(client: TestClient, guardian: str, session_id: str) -> None:
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children",
        headers=_auth(guardian),
        json={"first_name": "Robin", "date_of_birth": "2018-06-01"},
    ).json()["id"]
    pid = client.post(
        "/api/v1/booking/checkout",
        headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()["payment_id"]
    client.post(f"/api/v1/booking/payments/{pid}/confirm", headers=_auth(guardian))


def _broadcast(client: TestClient, owner: str, session_id: str, **kw):
    body = {"subject": "What to bring", "body": "Please pack a hat and water bottle.", **kw}
    return client.post(
        f"/api/v1/comms/sessions/{session_id}/broadcast", headers=_auth(owner), json=body
    )


def test_broadcast_reaches_booked_families(client: TestClient) -> None:
    owner, g1, g2 = _signup(client), _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    _book_confirm(client, g1, session_id)
    _book_confirm(client, g2, session_id)

    resp = _broadcast(client, owner, session_id, template_key="what_to_bring")
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["recipient_count"] == 2
    assert out["template_key"] == "what_to_bring"

    # Each family got it in their notifications inbox.
    for g in (g1, g2):
        notes = client.get("/api/v1/notifications", headers=_auth(g)).json()
        assert any(n["kind"] == "provider_broadcast" for n in notes)

    # It shows in the provider's sent history.
    history = client.get(
        f"/api/v1/comms/sessions/{session_id}/broadcasts", headers=_auth(owner)
    ).json()
    assert len(history) == 1
    assert history[0]["subject"] == "What to bring"


def test_only_confirmed_families_receive(client: TestClient) -> None:
    owner, g1, g2 = _signup(client), _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    _book_confirm(client, g1, session_id)
    # g2 holds+checks out but never confirms → not a recipient.
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(g2),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children",
        headers=_auth(g2),
        json={"first_name": "Sam", "date_of_birth": "2018-06-01"},
    ).json()["id"]
    client.post(
        "/api/v1/booking/checkout",
        headers=_auth(g2),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    )
    assert _broadcast(client, owner, session_id).json()["recipient_count"] == 1


def test_no_recipients_is_conflict(client: TestClient) -> None:
    owner = _signup(client)
    _, session_id = _org_and_session(client, owner)  # nobody booked
    assert _broadcast(client, owner, session_id).status_code == 409


def test_non_member_cannot_broadcast(client: TestClient) -> None:
    owner, outsider, guardian = _signup(client), _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    _book_confirm(client, guardian, session_id)
    assert _broadcast(client, outsider, session_id).status_code == 403
    assert (
        client.get(
            f"/api/v1/comms/sessions/{session_id}/broadcasts", headers=_auth(outsider)
        ).status_code
        == 403
    )
