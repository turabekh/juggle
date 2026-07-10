"""Inventory: seat holds decrement/restore availability, oversell is refused,
and — the make-or-break test — concurrent holds for the last seat never oversell.
"""

import uuid
from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread

from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session as SASession

from juggle.modules.catalog.core.models import Program, Venue
from juggle.modules.catalog.core.models import Session as ProgramSession
from juggle.modules.identity.core.models import UserAccount
from juggle.modules.inventory.core import service as inv
from juggle.modules.inventory.core.models import SeatHold, SeatHoldStatus
from juggle.modules.org.core.models import Organisation

_SESSION_BODY = {
    "starts_at": "2026-09-30T09:00:00Z",
    "ends_at": "2026-09-30T15:00:00Z",
    "price_cents": 5500,
    "age_min": 5,
    "age_max": 12,
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _published_session(client: TestClient, owner_token: str, *, capacity: int) -> str:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner_token), json={"name": f"Org {uuid.uuid4().hex[:6]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(owner_token),
        json={"organisation_id": org_id, "name": "Hall"},
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(owner_token),
        json={"organisation_id": org_id, "title": "Camp", "category": "art"},
    ).json()["id"]
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(owner_token),
        json={"venue_id": venue_id, "capacity": capacity, **_SESSION_BODY},
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner_token))
    return session_id


def _remaining(client: TestClient, session_id: str) -> int:
    resp = client.get(f"/api/v1/inventory/sessions/{session_id}/availability")
    return resp.json()["seats_remaining"]


def test_hold_decrements_and_release_restores(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=2)
    assert _remaining(client, session_id) == 2

    hold = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    )
    assert hold.status_code == 201, hold.text
    assert _remaining(client, session_id) == 1

    released = client.delete(
        f"/api/v1/inventory/holds/{hold.json()['id']}", headers=_auth(guardian)
    )
    assert released.status_code == 204
    assert _remaining(client, session_id) == 2


def test_holding_beyond_capacity_is_refused(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=1)

    first = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    )
    assert second.status_code == 409


def test_only_the_holder_can_release_a_hold(client: TestClient) -> None:
    owner, guardian_a, guardian_b = _signup(client), _signup(client), _signup(client)
    session_id = _published_session(client, owner, capacity=2)
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian_a),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]

    # A different guardian cannot release someone else's hold.
    assert (
        client.delete(f"/api/v1/inventory/holds/{hold_id}", headers=_auth(guardian_b)).status_code
        == 404
    )
    assert _remaining(client, session_id) == 1  # still held


def test_concurrent_holds_never_oversell(engine: Engine) -> None:
    """Eight threads race for a single seat. Exactly one may win."""
    with SASession(engine) as setup:
        org = Organisation(name="Race Co", slug=f"race-{uuid.uuid4().hex[:8]}")
        holder = UserAccount(email=f"holder-{uuid.uuid4().hex[:8]}@example.com")
        setup.add_all([org, holder])
        setup.flush()
        venue = Venue(organisation_id=org.id, name="Hall")
        program = Program(organisation_id=org.id, title="Camp", category="art")
        setup.add_all([venue, program])
        setup.flush()
        start = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)
        session = ProgramSession(
            program_id=program.id,
            venue_id=venue.id,
            starts_at=start,
            ends_at=start + timedelta(hours=6),
            capacity=1,
            seats_taken=0,
            price_cents=100,
            age_min=5,
            age_max=12,
        )
        setup.add(session)
        setup.commit()
        session_id, holder_id, org_id = session.id, holder.id, org.id

    n = 8
    barrier = Barrier(n)
    outcomes: list[str] = []

    def worker() -> None:
        barrier.wait()  # release all threads at once to maximise contention
        with SASession(engine) as ws:
            try:
                inv.hold_seats(ws, session_id=session_id, held_by_id=holder_id, quantity=1)
                ws.commit()
                outcomes.append("ok")
            except inv.SoldOut:
                ws.rollback()
                outcomes.append("soldout")
            except Exception as exc:  # pragma: no cover - surfaces unexpected failures
                ws.rollback()
                outcomes.append(f"err:{exc!r}")

    threads = [Thread(target=worker) for _ in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    try:
        assert outcomes.count("ok") == 1, outcomes
        assert outcomes.count("soldout") == n - 1, outcomes
        with SASession(engine) as check:
            final = check.get(ProgramSession, session_id)
            assert final is not None
            assert final.seats_taken == 1
            active = check.scalars(
                select(SeatHold).where(
                    SeatHold.session_id == session_id,
                    SeatHold.status == SeatHoldStatus.active,
                )
            ).all()
            assert len(active) == 1
    finally:
        with SASession(engine) as cleanup:
            cleanup.execute(delete(SeatHold).where(SeatHold.session_id == session_id))
            cleanup.execute(delete(ProgramSession).where(ProgramSession.id == session_id))
            cleanup.execute(delete(Program).where(Program.organisation_id == org_id))
            cleanup.execute(delete(Venue).where(Venue.organisation_id == org_id))
            cleanup.execute(delete(Organisation).where(Organisation.id == org_id))
            cleanup.execute(delete(UserAccount).where(UserAccount.id == holder_id))
            cleanup.commit()
