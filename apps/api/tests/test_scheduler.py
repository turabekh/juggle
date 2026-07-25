"""Scheduler (PRD §7.5, §7.7): one idempotent maintenance tick — expired-hold
reclaim, waitlist offer/expiry sweep, and T-48h/T-3h pre-session reminders that
fire exactly once per window. ``now`` is injected for deterministic timing."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from juggle.modules.scheduler.core import service

# A fixed future session start; tests pick `now` relative to it.
START = datetime(2027, 6, 1, 9, 0, tzinfo=UTC)
START_ISO = "2027-06-01T09:00:00Z"
END_ISO = "2027-06-01T15:00:00Z"


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_session(
    client: TestClient, owner: str, *, capacity=5, starts=START_ISO, ends=END_ISO
) -> tuple[str, str]:
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
            "starts_at": starts,
            "ends_at": ends,
            "capacity": capacity,
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


# --- reminders ---------------------------------------------------------------


def test_48h_reminder_fires_once(client: TestClient, db: Session) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_session(client, owner)
    _book_confirm(client, guardian, session_id)

    now = START - timedelta(hours=40)  # inside the 48h window, outside 3h
    first = service.run_due_jobs(db, now=now)
    assert first.reminders_sent == 1

    notes = client.get("/api/v1/notifications", headers=_auth(guardian)).json()
    reminders = [n for n in notes if n["kind"] == "session_reminder"]
    assert len(reminders) == 1
    assert "2 days" in reminders[0]["subject"]

    # A second tick at the same time does not re-send (deduped by marker).
    assert service.run_due_jobs(db, now=now).reminders_sent == 0


def test_far_off_session_gets_no_reminder(client: TestClient, db: Session) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_session(client, owner)
    _book_confirm(client, guardian, session_id)

    now = START - timedelta(days=10)  # way outside both windows
    assert service.run_due_jobs(db, now=now).reminders_sent == 0


def test_3h_and_48h_are_separate_windows(client: TestClient, db: Session) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_session(client, owner)
    _book_confirm(client, guardian, session_id)

    # Cross the 48h mark first.
    service.run_due_jobs(db, now=START - timedelta(hours=40))
    # Later, cross the 3h mark → a second, distinct reminder.
    later = service.run_due_jobs(db, now=START - timedelta(hours=2))
    assert later.reminders_sent == 1

    notes = client.get("/api/v1/notifications", headers=_auth(guardian)).json()
    assert sum(1 for n in notes if n["kind"] == "session_reminder") == 2


# --- hold reclaim ------------------------------------------------------------


def test_expired_holds_are_reclaimed(client: TestClient, db: Session) -> None:
    from juggle.modules.inventory.core.models import SeatHold

    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_session(client, owner, capacity=3)
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 2},
    ).json()["id"]

    avail_url = f"/api/v1/inventory/sessions/{session_id}/availability"
    assert client.get(avail_url).json()["seats_remaining"] == 1  # 3 - 2 held

    # Force the hold past its TTL, then sweep.
    hold = db.get(SeatHold, uuid.UUID(hold_id))
    assert hold is not None
    hold.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()

    summary = service.run_due_jobs(db, now=datetime.now(UTC))
    assert summary.holds_reclaimed == 1

    assert client.get(avail_url).json()["seats_remaining"] == 3  # seats given back


# --- admin trigger -----------------------------------------------------------


def test_run_endpoint_requires_admin(client: TestClient, make_admin) -> None:
    guardian = _signup(client)
    assert client.post("/api/v1/scheduler/run", headers=_auth(guardian)).status_code == 403

    admin = make_admin()
    resp = client.post("/api/v1/scheduler/run", headers=_auth(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "holds_reclaimed",
        "abandoned_checkouts_swept",
        "party_deposits_swept",
        "party_balances_processed",
        "waitlist_sessions_processed",
        "waitlist_offers_made",
        "waitlist_offers_expired",
        "reminders_sent",
        "what_to_bring_sent",
        "compliance_expired",
        "plans_resolved",
        "plans_swept",
        "plans_purged",
        "auth_rows_pruned",
        "quotes_expired",
    }


def test_expired_wwcc_is_marked_expired(client: TestClient, db: Session) -> None:
    owner = _signup(client)
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    wwcc = client.post(
        f"/api/v1/org/{org_id}/wwcc",
        headers=_auth(owner),
        json={"staff_name": "Coach", "wwcc_number": "WWC1", "expiry_date": "2020-01-01"},
    ).json()
    assert wwcc["status"] == "pending"

    summary = service.run_due_jobs(db, now=datetime.now(UTC))
    assert summary.compliance_expired >= 1

    after = client.get(f"/api/v1/org/{org_id}/wwcc", headers=_auth(owner)).json()
    assert after[0]["status"] == "expired"


def test_what_to_bring_sent_once(client: TestClient, db: Session) -> None:
    owner, guardian = _signup(client), _signup(client)
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
            "starts_at": START_ISO,
            "ends_at": END_ISO,
            "capacity": 5,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
            "what_to_bring": "A hat, sunscreen and a water bottle.",
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner))
    _book_confirm(client, guardian, session_id)

    now = START - timedelta(hours=20)  # inside the T-24h window
    first = service.run_due_jobs(db, now=now)
    assert first.what_to_bring_sent == 1
    notes = client.get("/api/v1/notifications", headers=_auth(guardian)).json()
    wtb = [n for n in notes if n["kind"] == "what_to_bring"]
    assert len(wtb) == 1
    # Idempotent — a second tick sends nothing more.
    assert service.run_due_jobs(db, now=now).what_to_bring_sent == 0


def test_no_what_to_bring_note_no_email(client: TestClient, db: Session) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_session(client, owner)  # no what_to_bring set
    _book_confirm(client, guardian, session_id)
    now = START - timedelta(hours=20)
    assert service.run_due_jobs(db, now=now).what_to_bring_sent == 0
