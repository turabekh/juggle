"""Anti-hoarding: a guardian's concurrent active seat holds are capped
(config-driven), returning 429; released/expired holds free a slot (PRD fraud
basics). Inventory correctness is the product, so this is enforced in the service."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _session(client: TestClient, owner: str, *, capacity: int = 10) -> str:
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
            "capacity": capacity,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    return session_id


def _set_cap(client: TestClient, admin: str, value: int) -> None:
    resp = client.put(
        "/api/v1/config/max_active_holds_per_guardian",
        headers=_auth(admin),
        json={"value": value},
    )
    assert resp.status_code == 200, resp.text


def _hold(client: TestClient, guardian: str, session_id: str):
    return client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    )


def test_cap_blocks_excess_holds(client: TestClient, make_admin) -> None:
    admin = make_admin()
    _set_cap(client, admin, 2)
    owner, guardian = _signup(client), _signup(client)
    session_id = _session(client, owner)

    assert _hold(client, guardian, session_id).status_code == 201
    assert _hold(client, guardian, session_id).status_code == 201
    third = _hold(client, guardian, session_id)
    assert third.status_code == 429
    assert "hold" in third.json()["detail"].lower()


def test_releasing_a_hold_frees_a_slot(client: TestClient, make_admin) -> None:
    admin = make_admin()
    _set_cap(client, admin, 1)
    owner, guardian = _signup(client), _signup(client)
    session_id = _session(client, owner)

    first = _hold(client, guardian, session_id)
    assert first.status_code == 201
    assert _hold(client, guardian, session_id).status_code == 429  # at cap

    # Release the first hold → a slot frees up.
    hold_id = first.json()["id"]
    assert (
        client.delete(f"/api/v1/inventory/holds/{hold_id}", headers=_auth(guardian)).status_code
        == 204
    )
    assert _hold(client, guardian, session_id).status_code == 201


def test_expired_holds_do_not_count(client: TestClient, make_admin, db: Session) -> None:
    from juggle.modules.inventory.core.models import SeatHold

    admin = make_admin()
    _set_cap(client, admin, 1)
    owner, guardian = _signup(client), _signup(client)
    session_id = _session(client, owner)

    first = _hold(client, guardian, session_id)
    assert first.status_code == 201

    # Age the hold past its TTL — it no longer counts toward the cap.
    hold = db.get(SeatHold, uuid.UUID(first.json()["id"]))
    assert hold is not None
    hold.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()

    assert _hold(client, guardian, session_id).status_code == 201


def test_default_cap_allows_normal_use(client: TestClient) -> None:
    # No config override → the built-in default (8) comfortably allows a handful.
    owner, guardian = _signup(client), _signup(client)
    session_id = _session(client, owner)
    for _ in range(5):
        assert _hold(client, guardian, session_id).status_code == 201
