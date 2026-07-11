"""Duplicate-from-last-cycle (PRD §8.2): a provider re-lists a program's sessions
shifted forward by whole days, preserving everything but resetting seats."""

import uuid
from datetime import datetime

from fastapi.testclient import TestClient


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _program_with_sessions(client: TestClient, owner: str, starts: list[str]) -> str:
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
    for start in starts:
        end = start.replace("09:00", "15:00")
        client.post(
            f"/api/v1/catalog/programs/{program_id}/sessions",
            headers=_auth(owner),
            json={
                "venue_id": venue_id,
                "starts_at": start,
                "ends_at": end,
                "capacity": 10,
                "price_cents": 5500,
                "age_min": 5,
                "age_max": 12,
                "what_to_bring": "A hat.",
            },
        )
    return program_id


def _dup(client: TestClient, owner: str, program_id: str, shift_days: int):
    return client.post(
        f"/api/v1/catalog/programs/{program_id}/duplicate-sessions",
        headers=_auth(owner),
        json={"shift_days": shift_days},
    )


def test_duplicates_all_sessions_shifted(client: TestClient) -> None:
    owner = _signup(client)
    program_id = _program_with_sessions(
        client, owner, ["2027-01-05T09:00:00Z", "2027-01-06T09:00:00Z"]
    )

    resp = _dup(client, owner, program_id, shift_days=7)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert len(created) == 2

    # Shifted by exactly 7 days, time-of-day preserved, attributes copied, seats reset.
    starts = sorted(s["starts_at"] for s in created)
    assert datetime.fromisoformat(starts[0]).day == 12  # 5 + 7
    assert datetime.fromisoformat(starts[1]).day == 13  # 6 + 7
    for s in created:
        assert s["capacity"] == 10
        assert s["price_cents"] == 5500
        assert s["seats_taken"] == 0
        assert s["seats_remaining"] == 10

    # The program now has the originals + the copies.
    total = client.get(
        f"/api/v1/catalog/programs/{program_id}/sessions", headers=_auth(owner)
    ).json()
    assert len(total) == 4


def test_cancelled_sessions_are_not_duplicated(client: TestClient) -> None:
    owner = _signup(client)
    program_id = _program_with_sessions(
        client, owner, ["2027-01-05T09:00:00Z", "2027-01-06T09:00:00Z"]
    )
    sessions = client.get(
        f"/api/v1/catalog/programs/{program_id}/sessions", headers=_auth(owner)
    ).json()
    # Cancel one session (provider-initiated).
    client.post(
        f"/api/v1/booking/sessions/{sessions[0]['id']}/cancel", headers=_auth(owner)
    )

    created = _dup(client, owner, program_id, shift_days=7).json()
    assert len(created) == 1  # only the non-cancelled one


def test_non_member_cannot_duplicate(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    program_id = _program_with_sessions(client, owner, ["2027-01-05T09:00:00Z"])
    assert _dup(client, outsider, program_id, shift_days=7).status_code == 403


def test_shift_must_be_positive(client: TestClient) -> None:
    owner = _signup(client)
    program_id = _program_with_sessions(client, owner, ["2027-01-05T09:00:00Z"])
    assert _dup(client, owner, program_id, shift_days=0).status_code == 422
