"""Reviews (PRD §7.6): verified-booking-only, completion-gated, child-PII
screened, moderated before public, provider right-of-reply.

A review requires a *completed* session, so these tests create sessions dated in
the past (the catalog only enforces ends_at > starts_at, not future-dating).
"""

import uuid

from fastapi.testclient import TestClient

PAST_START = "2020-01-11T09:00:00Z"
PAST_END = "2020-01-11T15:00:00Z"
FUTURE_START = "2030-09-30T09:00:00Z"
FUTURE_END = "2030-09-30T15:00:00Z"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _org_and_session(
    client: TestClient, owner_token: str, *, starts_at: str, ends_at: str
) -> tuple[str, str]:
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
            "starts_at": starts_at,
            "ends_at": ends_at,
            "capacity": 5,
            "price_cents": 5000,
            "age_min": 4,
            "age_max": 12,
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(owner_token))
    return org_id, session_id


def _book(client: TestClient, guardian: str, session_id: str, *, dob: str = "2014-06-01") -> str:
    hold_id = client.post(
        "/api/v1/inventory/holds",
        headers=_auth(guardian),
        json={"session_id": session_id, "quantity": 1},
    ).json()["id"]
    child_id = client.post(
        "/api/v1/identity/children",
        headers=_auth(guardian),
        json={"first_name": "Robin", "date_of_birth": dob},
    ).json()["id"]
    return client.post(
        "/api/v1/booking/checkout",
        headers=_auth(guardian),
        json={
            "idempotency_key": f"key-{uuid.uuid4().hex}",
            "items": [{"hold_id": hold_id, "children": [{"child_id": child_id}]}],
        },
    ).json()["payment_id"]


def _confirmed_booking_id(
    client: TestClient, guardian: str, session_id: str, *, dob: str = "2014-06-01"
) -> str:
    payment_id = _book(client, guardian, session_id, dob=dob)
    client.post(f"/api/v1/booking/payments/{payment_id}/confirm", headers=_auth(guardian))
    bookings = client.get("/api/v1/booking/bookings", headers=_auth(guardian)).json()
    return next(b["id"] for b in bookings if b["session_id"] == session_id)


def _submit(client: TestClient, guardian: str, booking_id: str, *, rating=5, body="Great fun"):
    return client.post(
        "/api/v1/reviews",
        headers=_auth(guardian),
        json={"booking_id": booking_id, "rating": rating, "body": body},
    )


# --- happy path + moderation -------------------------------------------------


def test_submit_moderate_and_publish(client: TestClient, make_admin) -> None:
    owner, guardian = _signup(client), _signup(client)
    org_id, session_id = _org_and_session(client, owner, starts_at=PAST_START, ends_at=PAST_END)
    booking_id = _confirmed_booking_id(client, guardian, session_id)

    resp = _submit(client, guardian, booking_id, rating=4, body="Kids had a blast")
    assert resp.status_code == 201, resp.text
    review = resp.json()
    assert review["status"] == "pending"
    assert review["rating"] == 4

    # Pending reviews are not public.
    public = client.get(f"/api/v1/reviews/organisations/{org_id}").json()
    assert public["summary"]["count"] == 0
    assert public["items"] == []

    # Admin moderates: approve.
    admin = make_admin()
    queue = client.get("/api/v1/reviews/moderation/queue", headers=_auth(admin)).json()
    assert any(r["id"] == review["id"] for r in queue)
    moderated = client.post(
        f"/api/v1/reviews/{review['id']}/moderate",
        headers=_auth(admin),
        json={"approve": True},
    )
    assert moderated.status_code == 200
    assert moderated.json()["status"] == "published"

    # Now it's public and the summary reflects it.
    public = client.get(f"/api/v1/reviews/organisations/{org_id}").json()
    assert public["summary"] == {"average": 4.0, "count": 1}
    assert public["items"][0]["body"] == "Kids had a blast"
    assert public["items"][0]["author_label"]  # a non-empty byline, never the child's name

    # Program-scoped listing agrees.
    prog_public = client.get(f"/api/v1/reviews/programs/{review['program_id']}").json()
    assert prog_public["summary"]["count"] == 1


def test_rejected_review_stays_hidden(client: TestClient, make_admin) -> None:
    owner, guardian = _signup(client), _signup(client)
    org_id, session_id = _org_and_session(client, owner, starts_at=PAST_START, ends_at=PAST_END)
    booking_id = _confirmed_booking_id(client, guardian, session_id)
    review = _submit(client, guardian, booking_id).json()

    admin = make_admin()
    rejected = client.post(
        f"/api/v1/reviews/{review['id']}/moderate",
        headers=_auth(admin),
        json={"approve": False, "reason": "spam"},
    ).json()
    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "spam"

    public = client.get(f"/api/v1/reviews/organisations/{org_id}").json()
    assert public["summary"]["count"] == 0


# --- verification gates ------------------------------------------------------


def test_cannot_review_before_session_completes(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(
        client, owner, starts_at=FUTURE_START, ends_at=FUTURE_END
    )
    booking_id = _confirmed_booking_id(client, guardian, session_id, dob="2023-06-01")
    resp = _submit(client, guardian, booking_id)
    assert resp.status_code == 409


def test_cannot_review_unconfirmed_booking(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, starts_at=PAST_START, ends_at=PAST_END)
    _book(client, guardian, session_id)  # checked out, never confirmed
    booking_id = client.get("/api/v1/booking/bookings", headers=_auth(guardian)).json()[0]["id"]
    resp = _submit(client, guardian, booking_id)
    assert resp.status_code == 409


def test_cannot_review_someone_elses_booking(client: TestClient) -> None:
    owner, guardian, outsider = _signup(client), _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, starts_at=PAST_START, ends_at=PAST_END)
    booking_id = _confirmed_booking_id(client, guardian, session_id)
    resp = _submit(client, outsider, booking_id)
    assert resp.status_code == 404


def test_one_review_per_booking(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, starts_at=PAST_START, ends_at=PAST_END)
    booking_id = _confirmed_booking_id(client, guardian, session_id)
    assert _submit(client, guardian, booking_id).status_code == 201
    assert _submit(client, guardian, booking_id).status_code == 409


def test_child_name_is_screened_out(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, starts_at=PAST_START, ends_at=PAST_END)
    booking_id = _confirmed_booking_id(client, guardian, session_id)
    # The seeded child is "Robin"; mentioning them is blocked (PRD §7.6).
    resp = _submit(client, guardian, booking_id, body="Robin absolutely loved the camp")
    assert resp.status_code == 422
    # A substring that isn't the whole word must NOT trip the screen.
    ok = _submit(client, guardian, booking_id, body="The robinstock craft was superb")
    assert ok.status_code == 201


def test_rating_bounds_rejected(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, starts_at=PAST_START, ends_at=PAST_END)
    booking_id = _confirmed_booking_id(client, guardian, session_id)
    assert _submit(client, guardian, booking_id, rating=0).status_code == 422
    assert _submit(client, guardian, booking_id, rating=6).status_code == 422


# --- reviewable-bookings helper ---------------------------------------------


def test_reviewable_bookings_lists_then_clears(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(client, owner, starts_at=PAST_START, ends_at=PAST_END)
    booking_id = _confirmed_booking_id(client, guardian, session_id)

    reviewable = client.get("/api/v1/reviews/reviewable", headers=_auth(guardian)).json()
    assert [r["booking_id"] for r in reviewable] == [booking_id]

    _submit(client, guardian, booking_id)
    after = client.get("/api/v1/reviews/reviewable", headers=_auth(guardian)).json()
    assert after == []


def test_future_booking_not_reviewable(client: TestClient) -> None:
    owner, guardian = _signup(client), _signup(client)
    _, session_id = _org_and_session(
        client, owner, starts_at=FUTURE_START, ends_at=FUTURE_END
    )
    _confirmed_booking_id(client, guardian, session_id, dob="2023-06-01")
    reviewable = client.get("/api/v1/reviews/reviewable", headers=_auth(guardian)).json()
    assert reviewable == []


# --- provider right-of-reply -------------------------------------------------


def test_provider_reply_flow(client: TestClient, make_admin) -> None:
    owner, guardian, outsider = _signup(client), _signup(client), _signup(client)
    org_id, session_id = _org_and_session(client, owner, starts_at=PAST_START, ends_at=PAST_END)
    booking_id = _confirmed_booking_id(client, guardian, session_id)
    review = _submit(client, guardian, booking_id).json()

    # Reply is blocked until the review is published.
    early = client.post(
        f"/api/v1/reviews/{review['id']}/reply",
        headers=_auth(owner),
        json={"reply": "Thanks!"},
    )
    assert early.status_code == 409

    admin = make_admin()
    client.post(
        f"/api/v1/reviews/{review['id']}/moderate", headers=_auth(admin), json={"approve": True}
    )

    # A non-member cannot reply.
    assert (
        client.post(
            f"/api/v1/reviews/{review['id']}/reply",
            headers=_auth(outsider),
            json={"reply": "hi"},
        ).status_code
        == 403
    )

    # The provider can.
    replied = client.post(
        f"/api/v1/reviews/{review['id']}/reply",
        headers=_auth(owner),
        json={"reply": "Thanks for coming!"},
    )
    assert replied.status_code == 200
    assert replied.json()["provider_reply"] == "Thanks for coming!"

    # And it surfaces publicly with the review.
    public = client.get(f"/api/v1/reviews/organisations/{org_id}").json()
    assert public["items"][0]["provider_reply"] == "Thanks for coming!"


def test_provider_list_requires_membership(client: TestClient) -> None:
    owner, outsider = _signup(client), _signup(client)
    org_id, _ = _org_and_session(client, owner, starts_at=PAST_START, ends_at=PAST_END)
    assert (
        client.get(f"/api/v1/reviews/provider/{org_id}", headers=_auth(outsider)).status_code
        == 403
    )
    assert (
        client.get(f"/api/v1/reviews/provider/{org_id}", headers=_auth(owner)).status_code == 200
    )


# --- admin gating ------------------------------------------------------------


def test_non_admin_cannot_access_moderation_queue(client: TestClient) -> None:
    guardian = _signup(client)
    assert (
        client.get("/api/v1/reviews/moderation/queue", headers=_auth(guardian)).status_code == 403
    )
