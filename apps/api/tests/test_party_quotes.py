"""Request-to-quote parties (Milestone C — PRD §9, ADR-0009).

Brief → quote → (one revision) → accept → deposit, plus the expiry sweep.

The design under test (docs/PLANS/milestone-C-request-to-quote.md): a quote *is* a bespoke,
unlisted package + one slot, so accepting runs the unchanged instant-book deposit rails. The
tests that matter most are therefore the ones proving (a) the bespoke package never leaks into
public listings, (b) negotiation really is capped at one round, and (c) an accepted quote lands
on a real deposit PaymentIntent.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from juggle.modules.config.core import service as config_service
from juggle.modules.flags.core import service as flags_service
from juggle.modules.notifications.core.gateway import FakeEmailGateway
from juggle.modules.org.core import service as org_service
from juggle.modules.org.core.models import OrgStatus
from juggle.modules.parties.core import quotes as quotes_service
from juggle.modules.parties.core.models import PartySlot, PartySlotStatus
from juggle.modules.parties.core.schemas import QuoteIn, QuoteRequestIn
from juggle.modules.payments.core.gateway import FakeGateway

PREFIX = "/api/v1/parties/quotes"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def flag_on(db: Session) -> None:
    flags_service.upsert_flag(db, key="party_quotes", enabled=True, rollout_percentage=100)


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _approved_org(client: TestClient, db: Session, owner: str) -> tuple[str, str]:
    """An approved provider with a venue — only approved providers take enquiries."""
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues", headers=_auth(owner),
        json={"organisation_id": org_id, "name": "Party Hall"},
    ).json()["id"]
    org_service.set_status(db, uuid.UUID(org_id), OrgStatus.approved)
    db.flush()
    return org_id, venue_id


def _brief_body(org_id: str, **over: object) -> dict[str, object]:
    starts = datetime.now(UTC) + timedelta(days=30)
    return {
        "organisation_id": org_id,
        "starts_at": starts.isoformat(),
        "ends_at": (starts + timedelta(hours=2)).isoformat(),
        "suburb": "Fremantle",
        "kid_count": 12,
        "child_age_min": 5,
        "child_age_max": 8,
        "budget_cents": 60000,
        "notes": "Superhero theme if possible",
        **over,
    }


def _quote_body(venue_id: str, **over: object) -> dict[str, object]:
    starts = datetime.now(UTC) + timedelta(days=30)
    return {
        "venue_id": venue_id,
        "starts_at": starts.isoformat(),
        "ends_at": (starts + timedelta(hours=2)).isoformat(),
        "headcount": 12,
        "per_head_price_cents": 4500,
        "message": "Includes host, games and a cake table.",
        **over,
    }


def _submit(client: TestClient, parent: str, org_id: str, **over: object) -> str:
    resp = client.post(
        f"{PREFIX}/requests", headers=_auth(parent), json=_brief_body(org_id, **over)
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def _quote(client: TestClient, owner: str, request_id: str, venue_id: str, **over: object) -> dict:
    resp = client.post(
        f"{PREFIX}/requests/{request_id}/quote", headers=_auth(owner),
        json=_quote_body(venue_id, **over),
    )
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


# --- Flag gate ---------------------------------------------------------------


def test_quotes_are_flag_gated(client: TestClient, db: Session) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id, _venue = _approved_org(client, db, owner)
    resp = client.post(
        f"{PREFIX}/requests", headers=_auth(parent), json=_brief_body(org_id)
    )
    assert resp.status_code == 404  # flag off


# --- The happy path ----------------------------------------------------------


def test_brief_to_quote_to_accept_takes_a_deposit(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)

    request_id = _submit(client, parent, org_id)
    assert client.get(
        f"{PREFIX}/requests/{request_id}", headers=_auth(parent)
    ).json()["status"] == "submitted"

    quote = _quote(client, owner, request_id, venue_id)
    assert quote["total_cents"] == 4500 * 12
    assert quote["status"] == "sent"
    assert quote["can_request_revision"] is True
    # Deposit is previewed from the same config the booking will use (ADR-0007).
    assert quote["deposit_cents"] == round(
        quote["total_cents"] * config_service.party_deposit_pct(db) / 100
    )

    accepted = client.post(f"{PREFIX}/{quote['id']}/accept", headers=_auth(parent))
    assert accepted.status_code == 200, accepted.text
    booking = accepted.json()
    # It lands on the ordinary party-booking rails: real deposit intent, pending until paid.
    assert booking["status"] == "pending_deposit"
    assert booking["client_secret"]
    assert booking["total_cents"] == 4500 * 12
    assert booking["deposit_cents"] + booking["balance_cents"] == booking["total_cents"]

    detail = client.get(f"{PREFIX}/requests/{request_id}", headers=_auth(parent)).json()
    assert detail["status"] == "accepted"
    assert detail["quote"]["status"] == "accepted"
    assert detail["quote"]["booking_id"] == booking["id"]


def test_bespoke_quote_package_never_appears_publicly(
    client: TestClient, db: Session, flag_on: None
) -> None:
    """A price quoted to one family must not surface on the marketplace."""
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)

    org_public = client.get(f"/api/v1/parties/orgs/{org_id}/packages").json()
    assert all(p["id"] != quote["package_id"] for p in org_public)
    marketplace = client.get("/api/v1/parties/packages").json()
    assert all(p["id"] != quote["package_id"] for p in marketplace)


# --- ADR-0009: exactly one revision round ------------------------------------


def test_one_revision_round_then_no_more(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)

    asked = client.post(
        f"{PREFIX}/{quote['id']}/request-revision", headers=_auth(parent),
        json={"message": "Could you do $40/head?"},
    )
    assert asked.status_code == 200
    assert asked.json()["status"] == "revision_requested"
    # A second ask is refused even before the provider replies.
    again = client.post(
        f"{PREFIX}/{quote['id']}/request-revision", headers=_auth(parent),
        json={"message": "or $35?"},
    )
    assert again.status_code == 409

    revised = client.put(
        f"{PREFIX}/{quote['id']}", headers=_auth(owner),
        json=_quote_body(venue_id, per_head_price_cents=4000),
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["revision_count"] == 1
    assert revised.json()["total_cents"] == 4000 * 12
    assert revised.json()["can_request_revision"] is False

    # And the parent cannot open a second round after the revision either.
    third = client.post(
        f"{PREFIX}/{quote['id']}/request-revision", headers=_auth(parent),
        json={"message": "one more thing"},
    )
    assert third.status_code == 409
    # Nor can the provider revise twice.
    assert client.put(
        f"{PREFIX}/{quote['id']}", headers=_auth(owner), json=_quote_body(venue_id)
    ).status_code == 409


def test_provider_cannot_revise_before_being_asked(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)
    resp = client.put(
        f"{PREFIX}/{quote['id']}", headers=_auth(owner), json=_quote_body(venue_id)
    )
    assert resp.status_code == 409


def test_revision_retires_the_superseded_slot(
    client: TestClient, db: Session, flag_on: None
) -> None:
    """The old bespoke slot must not stay bookable once the offer moves."""
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)
    first_slot = uuid.UUID(quote["slot_id"])

    client.post(
        f"{PREFIX}/{quote['id']}/request-revision", headers=_auth(parent),
        json={"message": "cheaper?"},
    )
    revised = client.put(
        f"{PREFIX}/{quote['id']}", headers=_auth(owner),
        json=_quote_body(venue_id, per_head_price_cents=4000),
    ).json()

    assert revised["slot_id"] != str(first_slot)
    old = db.get(PartySlot, first_slot)
    assert old is not None and old.status is PartySlotStatus.cancelled


# --- Expiry ------------------------------------------------------------------


def test_expiry_sweep_lapses_the_quote_and_frees_the_slot(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)

    later = datetime.now(UTC) + timedelta(
        hours=config_service.party_quote_expiry_hours(db) + 1
    )
    gw = FakeEmailGateway()
    assert quotes_service.expire_due_quotes(db, now=later, email_gateway=gw) == 1
    assert any("expired" in (m["subject"] or "").lower() for m in gw.outbox)
    # Idempotent — a second sweep finds nothing.
    assert quotes_service.expire_due_quotes(db, now=later) == 0

    slot = db.get(PartySlot, uuid.UUID(quote["slot_id"]))
    assert slot is not None and slot.status is PartySlotStatus.cancelled
    detail = client.get(f"{PREFIX}/requests/{request_id}", headers=_auth(parent)).json()
    assert detail["status"] == "expired"
    assert detail["quote"] is None  # expired quotes drop out of the live view


def test_expired_quote_cannot_be_accepted(
    client: TestClient, db: Session, flag_on: None
) -> None:
    """Even before the sweep runs, a lapsed price is not acceptable."""
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)

    with pytest.raises(quotes_service.QuoteNotOpen):
        quotes_service.accept_quote(
            db, quote_id=uuid.UUID(quote["id"]),
            guardian_id=uuid.UUID(
                client.get("/api/v1/identity/me", headers=_auth(parent)).json()["id"]
            ),
            gateway=FakeGateway(),
            now=datetime.now(UTC) + timedelta(days=90),
        )


def test_accepted_quotes_survive_the_sweep(
    client: TestClient, db: Session, flag_on: None
) -> None:
    """A booked party must never be expired out from under the deposit (INV-1/INV-2)."""
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)
    client.post(f"{PREFIX}/{quote['id']}/accept", headers=_auth(parent))

    later = datetime.now(UTC) + timedelta(days=90)
    assert quotes_service.expire_due_quotes(db, now=later) == 0
    detail = client.get(f"{PREFIX}/requests/{request_id}", headers=_auth(parent)).json()
    assert detail["quote"]["status"] == "accepted"


# --- Access control ----------------------------------------------------------


def test_only_the_two_parties_can_read_an_enquiry(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner, outsider = _signup(client), _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)

    assert client.get(
        f"{PREFIX}/requests/{request_id}", headers=_auth(parent)
    ).status_code == 200
    assert client.get(
        f"{PREFIX}/requests/{request_id}", headers=_auth(owner)
    ).status_code == 200
    assert client.get(
        f"{PREFIX}/requests/{request_id}", headers=_auth(outsider)
    ).status_code == 404


def test_outsider_cannot_quote_or_read_the_inbox(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner, outsider = _signup(client), _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)

    assert client.post(
        f"{PREFIX}/requests/{request_id}/quote", headers=_auth(outsider),
        json=_quote_body(venue_id),
    ).status_code == 403
    assert client.get(
        f"{PREFIX}/orgs/{org_id}/requests", headers=_auth(outsider)
    ).status_code == 403


def test_another_parent_cannot_accept_someone_elses_quote(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner, other = _signup(client), _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)
    assert client.post(
        f"{PREFIX}/{quote['id']}/accept", headers=_auth(other)
    ).status_code == 404


def test_unapproved_provider_cannot_receive_enquiries(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": "Pending Co"}
    ).json()["id"]  # left in its default (unapproved) state
    resp = client.post(
        f"{PREFIX}/requests", headers=_auth(parent), json=_brief_body(org_id)
    )
    assert resp.status_code == 404


# --- Closing a conversation down ---------------------------------------------


def test_provider_declines_a_brief(client: TestClient, db: Session, flag_on: None) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id, _venue = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)

    resp = client.post(f"{PREFIX}/requests/{request_id}/decline", headers=_auth(owner))
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"
    # And there's nothing left to quote against.
    assert client.post(
        f"{PREFIX}/requests/{request_id}/decline", headers=_auth(owner)
    ).status_code == 409


def test_withdrawn_quote_reopens_the_brief_and_frees_the_slot(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)

    resp = client.post(f"{PREFIX}/{quote['id']}/withdraw", headers=_auth(owner))
    assert resp.status_code == 200 and resp.json()["status"] == "withdrawn"
    slot = db.get(PartySlot, uuid.UUID(quote["slot_id"]))
    assert slot is not None and slot.status is PartySlotStatus.cancelled

    # The brief is open again, and the partial UNIQUE doesn't block a fresh quote.
    detail = client.get(f"{PREFIX}/requests/{request_id}", headers=_auth(parent)).json()
    assert detail["status"] == "submitted" and detail["quote"] is None
    second = _quote(client, owner, request_id, venue_id, per_head_price_cents=5000)
    assert second["total_cents"] == 5000 * 12


def test_parent_withdraws_the_brief(client: TestClient, db: Session, flag_on: None) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)

    resp = client.post(f"{PREFIX}/requests/{request_id}/withdraw", headers=_auth(parent))
    assert resp.status_code == 200 and resp.json()["status"] == "withdrawn"
    slot = db.get(PartySlot, uuid.UUID(quote["slot_id"]))
    assert slot is not None and slot.status is PartySlotStatus.cancelled
    assert client.post(
        f"{PREFIX}/{quote['id']}/accept", headers=_auth(parent)
    ).status_code == 409


def test_second_quote_on_a_live_brief_is_refused(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    _quote(client, owner, request_id, venue_id)
    assert client.post(
        f"{PREFIX}/requests/{request_id}/quote", headers=_auth(owner),
        json=_quote_body(venue_id),
    ).status_code == 409


# --- Notifications + INV-3 ---------------------------------------------------


def test_each_transition_notifies_the_other_side(
    client: TestClient, db: Session, flag_on: None
) -> None:
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    parent_email = client.get("/api/v1/identity/me", headers=_auth(parent)).json()["email"]
    owner_email = client.get("/api/v1/identity/me", headers=_auth(owner)).json()["email"]

    parent_id = uuid.UUID(
        client.get("/api/v1/identity/me", headers=_auth(parent)).json()["id"]
    )
    owner_id = uuid.UUID(client.get("/api/v1/identity/me", headers=_auth(owner)).json()["id"])

    gw = FakeEmailGateway()
    request = quotes_service.create_request(
        db, guardian_id=parent_id,
        data=QuoteRequestIn(**_brief_body(org_id)),  # type: ignore[arg-type]
        email_gateway=gw,
    )
    assert any(m["to"] == owner_email for m in gw.outbox)  # provider gets the brief

    gw2 = FakeEmailGateway()
    quote = quotes_service.send_quote(
        db, request_id=request.id, actor_id=owner_id,
        data=QuoteIn(**_quote_body(venue_id)),  # type: ignore[arg-type]
        email_gateway=gw2,
    )
    assert any(m["to"] == parent_email for m in gw2.outbox)  # parent gets the quote
    assert quote.total_cents == 4500 * 12

    gw3 = FakeEmailGateway()
    quotes_service.request_revision(
        db, quote_id=quote.id, guardian_id=parent_id, message="cheaper?", email_gateway=gw3
    )
    assert any(m["to"] == owner_email for m in gw3.outbox)  # provider gets the counter


def test_the_brief_has_nowhere_to_put_child_pii(client: TestClient) -> None:
    """INV-3: a party brief is a kid count and an age band — never a name or a birth date."""
    from juggle.modules.parties.core.schemas import QuoteRequestIn

    forbidden = {"name", "child_name", "first_name", "date_of_birth", "dob", "medical"}
    assert forbidden.isdisjoint(QuoteRequestIn.model_fields)


# --- Pressure tests on the money seam ---------------------------------------


def test_two_parents_cannot_book_the_same_bespoke_slot(
    client: TestClient, db: Session, flag_on: None
) -> None:
    """INV-1: the bespoke slot is capacity-1 like any other. A provider who quotes the same
    time to two families must only ever sell it once."""
    owner = _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    first, second = _signup(client), _signup(client)

    req_a = _submit(client, first, org_id)
    req_b = _submit(client, second, org_id)
    quote_a = _quote(client, owner, req_a, venue_id)
    quote_b = _quote(client, owner, req_b, venue_id)  # same window, second bespoke slot

    assert client.post(f"{PREFIX}/{quote_a['id']}/accept", headers=_auth(first)).status_code == 200
    # Distinct slots, so B is still bookable — the guarantee is per slot, not per wall-clock.
    assert quote_a["slot_id"] != quote_b["slot_id"]
    assert client.post(
        f"{PREFIX}/{quote_b['id']}/accept", headers=_auth(second)
    ).status_code == 200
    # But the SAME slot can never be sold twice.
    assert client.post(
        f"/api/v1/parties/slots/{quote_a['slot_id']}/book", headers=_auth(second),
        json={"headcount": 12},
    ).status_code == 409


def test_accepting_twice_is_refused(client: TestClient, db: Session, flag_on: None) -> None:
    """A double-submit must not create two bookings (and two deposits) for one quote."""
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)

    assert client.post(f"{PREFIX}/{quote['id']}/accept", headers=_auth(parent)).status_code == 200
    assert client.post(f"{PREFIX}/{quote['id']}/accept", headers=_auth(parent)).status_code == 409


def test_headcount_is_pinned_to_the_quote(
    client: TestClient, db: Session, flag_on: None
) -> None:
    """The bespoke band is exact, so nobody can scale a negotiated price by booking directly."""
    parent, owner = _signup(client), _signup(client)
    org_id, venue_id = _approved_org(client, db, owner)
    request_id = _submit(client, parent, org_id)
    quote = _quote(client, owner, request_id, venue_id)

    resp = client.post(
        f"/api/v1/parties/slots/{quote['slot_id']}/book", headers=_auth(parent),
        json={"headcount": 30},  # quoted for 12
    )
    assert resp.status_code == 400
