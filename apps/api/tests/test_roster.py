"""Roster: providers see their confirmed attendees (with child PII + CSV);
outsiders are blocked; only confirmed bookings appear."""

import csv
import io
import uuid

from fastapi.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_and_session(client: TestClient, owner_token: str) -> tuple[str, str]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner_token), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
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
        json={
            "venue_id": venue_id,
            "starts_at": "2026-09-30T09:00:00Z",
            "ends_at": "2026-09-30T15:00:00Z",
            "capacity": 5,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner_token))
    return org_id, session_id


def _book(
    client: TestClient, guardian: str, session_id: str, *, dob: str, form: dict | None = None
) -> str:
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children",
        headers=_auth(guardian),
        json={
            "first_name": "Robin",
            "date_of_birth": dob,
            "medical_notes": "peanut allergy",
            "emergency_contact_name": "Gran",
            "emergency_contact_phone": "0400000000",
        },
    ).json()["id"]
    order = client.post(
        "/api/v1/booking/checkout",
        headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [
                {
                    "hold_id": hold_id,
                    "children": [{"child_id": child_id, "form_answers": form or {}}],
                }
            ],
        },
    ).json()
    return order["payment_id"]


def test_roster_lists_confirmed_children_with_pii(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    payment_id = _book(
        client, guardian, session_id, dob="2018-06-01", form={"swim_level": "beginner"}
    )
    client.post(f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian))

    roster = client.get(f"/api/v1/roster/sessions/{session_id}", headers=_auth(owner))
    assert roster.status_code == 200, roster.text
    body = roster.json()
    assert body["count"] == 1
    row = body["rows"][0]
    assert row["child_first_name"] == "Robin"
    assert row["age"] == 8  # born 2018, session Sep 2026
    assert row["medical_notes"] == "peanut allergy"
    assert row["emergency_contact_phone"] == "0400000000"
    assert row["form_answers"] == {"swim_level": "beginner"}


def test_pending_bookings_are_not_on_the_roster(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    _book(client, guardian, session_id, dob="2018-06-01")  # checked out but NOT confirmed

    roster = client.get(f"/api/v1/roster/sessions/{session_id}", headers=_auth(owner)).json()
    assert roster["count"] == 0


def test_non_member_cannot_view_roster(client: TestClient) -> None:
    owner, guardian, outsider = _signup(client), _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    payment_id = _book(client, guardian, session_id, dob="2018-06-01")
    client.post(f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian))

    assert (
        client.get(f"/api/v1/roster/sessions/{session_id}", headers=_auth(outsider)).status_code
        == 403
    )
    # Even the booked guardian is not a provider member.
    assert (
        client.get(f"/api/v1/roster/sessions/{session_id}", headers=_auth(guardian)).status_code
        == 403
    )


def test_csv_export(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    payment_id = _book(client, guardian, session_id, dob="2018-06-01")
    client.post(f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian))

    resp = client.get(
        f"/api/v1/roster/sessions/{session_id}/export.csv", headers=_auth(owner)
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    reader = list(csv.reader(io.StringIO(resp.text)))
    assert reader[0] == [
        "child_first_name",
        "age",
        "attended",
        "medical_notes",
        "emergency_contact_name",
        "emergency_contact_phone",
        "form_answers",
    ]
    assert reader[1][0] == "Robin"
    assert reader[1][2] == "no"  # not checked in
    assert reader[1][3] == "peanut allergy"


# --- attendance check-in (PRD §8.3) -----------------------------------------


def _confirmed_roster(client: TestClient, owner: str, guardian: str, session_id: str) -> dict:
    payment_id = _book(client, guardian, session_id, dob="2018-06-01")
    client.post(f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian))
    return client.get(f"/api/v1/roster/sessions/{session_id}", headers=_auth(owner)).json()


def test_mark_and_unmark_attendance(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    roster = _confirmed_roster(client, owner, guardian, session_id)
    assert roster["attended_count"] == 0
    assert roster["rows"][0]["attended"] is False
    bc_id = roster["rows"][0]["booking_child_id"]

    marked = client.put(
        f"/api/v1/roster/sessions/{session_id}/attendance/{bc_id}",
        headers=_auth(owner),
        json={"attended": True},
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["attended"] is True
    assert marked.json()["attended_at"] is not None

    after = client.get(f"/api/v1/roster/sessions/{session_id}", headers=_auth(owner)).json()
    assert after["attended_count"] == 1
    assert after["rows"][0]["attended"] is True

    # Undo the check-in.
    client.put(
        f"/api/v1/roster/sessions/{session_id}/attendance/{bc_id}",
        headers=_auth(owner),
        json={"attended": False},
    )
    reverted = client.get(f"/api/v1/roster/sessions/{session_id}", headers=_auth(owner)).json()
    assert reverted["attended_count"] == 0
    assert reverted["rows"][0]["attended"] is False


def test_attendance_shows_in_csv(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    roster = _confirmed_roster(client, owner, guardian, session_id)
    bc_id = roster["rows"][0]["booking_child_id"]
    client.put(
        f"/api/v1/roster/sessions/{session_id}/attendance/{bc_id}",
        headers=_auth(owner),
        json={"attended": True},
    )
    resp = client.get(
        f"/api/v1/roster/sessions/{session_id}/export.csv", headers=_auth(owner)
    )
    reader = list(csv.reader(io.StringIO(resp.text)))
    assert reader[1][2] == "yes"  # attended column


def test_non_member_cannot_mark_attendance(client: TestClient) -> None:
    owner, guardian, outsider = _signup(client), _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner)
    roster = _confirmed_roster(client, owner, guardian, session_id)
    bc_id = roster["rows"][0]["booking_child_id"]
    resp = client.put(
        f"/api/v1/roster/sessions/{session_id}/attendance/{bc_id}",
        headers=_auth(outsider),
        json={"attended": True},
    )
    assert resp.status_code == 403


def test_mark_unknown_child_is_404(client: TestClient) -> None:
    owner = _signup(client)
    _, session_id = _org_and_session(client, owner)
    resp = client.put(
        f"/api/v1/roster/sessions/{session_id}/attendance/{uuid.uuid4()}",
        headers=_auth(owner),
        json={"attended": True},
    )
    assert resp.status_code == 404
