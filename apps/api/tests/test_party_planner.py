"""Party Planner (ADR-0011 Milestone A): plan → RSVP + vote → resolve → confirm booking.

Covers the state machine, one-vote/edit-until-deadline, option-swap void, approval queue,
double-confirm locking, headcount band, tie-break, vote anonymity, no-child-PII, marketing
consent survival, rate limiting, and no-enumeration. Resolution is clock-controlled by calling
the scheduler service directly with a fixed ``now``.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from juggle.modules.config.core import service as config_service
from juggle.modules.flags.core import service as flags_service
from juggle.modules.notifications.core.gateway import FakeEmailGateway
from juggle.modules.notifications.core.models import NotificationLog
from juggle.modules.party_planner.core import service as planner_service
from juggle.modules.party_planner.core.models import (
    PartyPlan,
    PlanInvite,
    PlanMarketingConsent,
    PlanVote,
)
from juggle.modules.payments.core.gateway import FakeGateway

PREFIX = "/api/v1/party-planner"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def flag_on(db: Session) -> None:
    flags_service.upsert_flag(db, key="party_planner", enabled=True, rollout_percentage=100)


def _signup(client: TestClient) -> str:
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _package_with_slots(
    client: TestClient, owner: str, *, n_slots: int = 2, days_out: int = 12,
    min_headcount: int = 8, max_headcount: int = 20,
) -> tuple[str, list[str]]:
    org_id = client.post(
        "/api/v1/org", headers=_auth(owner), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues", headers=_auth(owner),
        json={"organisation_id": org_id, "name": "Party Hall"},
    ).json()["id"]
    pkg = client.post(
        f"/api/v1/parties/orgs/{org_id}/packages", headers=_auth(owner),
        json={"venue_id": venue_id, "name": "Superhero Party", "per_head_price_cents": 3500,
              "min_headcount": min_headcount, "max_headcount": max_headcount, "outdoor": False},
    ).json()
    base = datetime.now(UTC) + timedelta(days=days_out)
    slots = client.post(
        f"/api/v1/parties/packages/{pkg['id']}/slots", headers=_auth(owner),
        json={"slots": [
            {"starts_at": (base + timedelta(days=i)).isoformat(),
             "ends_at": (base + timedelta(days=i, hours=2)).isoformat()}
            for i in range(n_slots)
        ]},
    ).json()
    return pkg["id"], [s["id"] for s in slots]


def _build_open_plan(
    client: TestClient, host: str, package_id: str, slot_ids: list[str], *,
    custom: bool = True, deadline_days: int = 2, rank_favourite: int | None = None,
) -> dict:
    """Create a draft, add two package options (+ optional custom), rank, set deadline, open."""
    plan = client.post(f"{PREFIX}/plans", headers=_auth(host), json={"theme": "dino"}).json()
    pid = plan["id"]
    for slot_id in slot_ids[:2]:
        client.post(f"{PREFIX}/plans/{pid}/options/package", headers=_auth(host),
                    json={"package_id": package_id, "slot_id": slot_id})
    if custom:
        client.post(f"{PREFIX}/plans/{pid}/options/custom", headers=_auth(host),
                    json={"text": "Backyard party at ours"})
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    option_ids = [o["id"] for o in view["options"]]
    if rank_favourite is not None:
        ordered = [option_ids[rank_favourite]] + [
            o for i, o in enumerate(option_ids) if i != rank_favourite
        ]
        client.put(f"{PREFIX}/plans/{pid}/ranking", headers=_auth(host),
                   json={"option_ids": ordered})
    deadline = (datetime.now(UTC) + timedelta(days=deadline_days)).isoformat()
    client.put(f"{PREFIX}/plans/{pid}/deadline", headers=_auth(host),
               json={"deadline_at": deadline})
    opened = client.post(f"{PREFIX}/plans/{pid}/open", headers=_auth(host)).json()
    return opened


def _rsvp(client: TestClient, token: str, *, attending: bool = True, kid_count: int = 2,
          nickname: str = "The Smiths", email: str | None = None) -> str:
    body = {"parent_name": "Alex", "email": email or f"g-{uuid.uuid4().hex[:6]}@example.com",
            "attending": attending, "kid_count": kid_count, "nickname": nickname}
    return client.post(f"{PREFIX}/public/{token}/rsvp", json=body).json()["invite_token"]


def _resolve(db: Session, when: datetime) -> int:
    n = planner_service.resolve_due_plans(db, now=when)
    return n


# --- Flag gate --------------------------------------------------------------


def test_routes_404_when_flag_off(client: TestClient) -> None:
    host = _signup(client)
    resp = client.post(f"{PREFIX}/plans", headers=_auth(host), json={"theme": "dino"})
    assert resp.status_code == 404


# --- Happy path -------------------------------------------------------------


def test_full_vote_to_book_flow(client: TestClient, db: Session, flag_on: None) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    assert token and opened["status"] == "open"

    # Public view: 3 options, live availability true, no votes yet.
    pub = client.get(f"{PREFIX}/public/{token}").json()
    assert pub["is_open"] and len(pub["options"]) == 3
    pkg_options = [o for o in pub["options"] if o["kind"] == "package"]
    assert all(o["available"] for o in pkg_options)

    # Two guests RSVP (approval pending by default) → not on board/tally yet.
    inv1 = _rsvp(client, token, kid_count=6)
    inv2 = _rsvp(client, token, kid_count=4)
    pub = client.get(f"{PREFIX}/public/{token}").json()
    assert pub["rsvp_count"] == 0  # unapproved

    # Host approves both.
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    for inv in view["invites"]:
        client.post(f"{PREFIX}/plans/{pid}/invites/{inv['id']}/approve", headers=_auth(host))

    winning_option = pkg_options[0]["id"]
    client.put(f"{PREFIX}/invite/{inv1}/vote", json={"option_id": winning_option})
    client.put(f"{PREFIX}/invite/{inv2}/vote", json={"option_id": winning_option})
    pub = client.get(f"{PREFIX}/public/{token}").json()
    assert pub["rsvp_count"] == 2
    won = next(o for o in pub["options"] if o["id"] == winning_option)
    assert won["votes"] == 2

    # Deadline passes → resolve → winner is the voted package option.
    resolved = _resolve(db, datetime.now(UTC) + timedelta(days=3))
    assert resolved == 1
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    assert view["status"] == "resolved" and view["winning_option_id"] == winning_option

    # Host confirms → a party booking with headcount = Σ approved yes kid_count (6+4=10).
    confirmed = client.post(f"{PREFIX}/plans/{pid}/confirm", headers=_auth(host), json={}).json()
    assert confirmed["status"] == "booked" and confirmed["booking_id"]


# --- One vote + edit-until-deadline ----------------------------------------


def test_one_vote_per_invite_edit_in_place(client: TestClient, db: Session, flag_on: None) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv = _rsvp(client, token)
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    client.post(f"{PREFIX}/plans/{pid}/invites/{view['invites'][0]['id']}/approve",
                headers=_auth(host))
    opts = [o["id"] for o in view["options"] if o["kind"] == "package"]

    client.put(f"{PREFIX}/invite/{inv}/vote", json={"option_id": opts[0]})
    client.put(f"{PREFIX}/invite/{inv}/vote", json={"option_id": opts[1]})  # change vote
    count = db.scalar(select(func.count()).select_from(PlanVote))
    assert count == 1  # one row, edited in place
    pub = client.get(f"{PREFIX}/public/{token}").json()
    tally = {o["id"]: o["votes"] for o in pub["options"]}
    assert tally[opts[0]] == 0 and tally[opts[1]] == 1


def test_vote_rejected_after_resolution(client: TestClient, db: Session, flag_on: None) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv = _rsvp(client, token)
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    client.post(f"{PREFIX}/plans/{pid}/invites/{view['invites'][0]['id']}/approve",
                headers=_auth(host))
    _resolve(db, datetime.now(UTC) + timedelta(days=3))
    opt = next(o["id"] for o in view["options"] if o["kind"] == "package")
    resp = client.put(f"{PREFIX}/invite/{inv}/vote", json={"option_id": opt})
    assert resp.status_code == 409  # voting closed


# --- Approval queue + option void ------------------------------------------


def test_pending_rsvp_excluded_until_approved(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    _rsvp(client, token, nickname="Pending Pat")
    pub = client.get(f"{PREFIX}/public/{token}").json()
    assert pub["rsvp_count"] == 0 and pub["board"] == []
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    assert view["invites"][0]["status"] == "pending"


def test_removing_voted_option_voids_its_tally(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv = _rsvp(client, token)
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    client.post(f"{PREFIX}/plans/{pid}/invites/{view['invites'][0]['id']}/approve",
                headers=_auth(host))
    opt = next(o["id"] for o in view["options"] if o["kind"] == "package")
    client.put(f"{PREFIX}/invite/{inv}/vote", json={"option_id": opt})
    # Host removes the voted option → excluded from the live tally.
    client.request("DELETE", f"{PREFIX}/plans/{pid}/options/{opt}", headers=_auth(host))
    pub = client.get(f"{PREFIX}/public/{token}").json()
    assert all(o["id"] != opt for o in pub["options"])


# --- Double-confirm lock + headcount band ----------------------------------


def test_double_confirm_books_once(client: TestClient, db: Session, flag_on: None) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv = _rsvp(client, token, kid_count=10)
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    client.post(f"{PREFIX}/plans/{pid}/invites/{view['invites'][0]['id']}/approve",
                headers=_auth(host))
    opt = next(o["id"] for o in view["options"] if o["kind"] == "package")
    client.put(f"{PREFIX}/invite/{inv}/vote", json={"option_id": opt})
    _resolve(db, datetime.now(UTC) + timedelta(days=3))

    first = client.post(f"{PREFIX}/plans/{pid}/confirm", headers=_auth(host), json={})
    second = client.post(f"{PREFIX}/plans/{pid}/confirm", headers=_auth(host), json={})
    assert first.status_code == 200 and first.json()["status"] == "booked"
    assert second.status_code == 409  # already booked; no second deposit


def test_confirm_headcount_band_and_override(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host, min_headcount=8, max_headcount=20)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv = _rsvp(client, token, kid_count=3)  # below the package minimum of 8
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    client.post(f"{PREFIX}/plans/{pid}/invites/{view['invites'][0]['id']}/approve",
                headers=_auth(host))
    opt = next(o["id"] for o in view["options"] if o["kind"] == "package")
    client.put(f"{PREFIX}/invite/{inv}/vote", json={"option_id": opt})
    _resolve(db, datetime.now(UTC) + timedelta(days=3))

    auto = client.post(f"{PREFIX}/plans/{pid}/confirm", headers=_auth(host), json={})
    assert auto.status_code == 400  # Σ yes (3) is out of band
    override = client.post(f"{PREFIX}/plans/{pid}/confirm", headers=_auth(host),
                           json={"headcount": 10})
    assert override.status_code == 200 and override.json()["status"] == "booked"


# --- Tie-break --------------------------------------------------------------


def test_tiebreak_uses_birthday_kid_ranking(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    # Favourite = first option (index 0); no votes → tie broken to the favourite.
    opened = _build_open_plan(client, host, package_id, slots, custom=False, rank_favourite=0)
    pid = opened["id"]
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    favourite = view["options"][0]["id"]
    _resolve(db, datetime.now(UTC) + timedelta(days=3))
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    assert view["winning_option_id"] == favourite


def test_genuine_tie_leaves_host_to_choose(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots, custom=False)  # no ranking
    pid, token = opened["id"], opened["share_token"]
    _resolve(db, datetime.now(UTC) + timedelta(days=3))
    pub = client.get(f"{PREFIX}/public/{token}").json()
    assert pub["status"] == "resolved" and pub["is_tie"] and pub["winner_option_id"] is None
    # Host must pass an explicit option to confirm.
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    opt = next(o["id"] for o in view["options"] if o["kind"] == "package")
    confirmed = client.post(f"{PREFIX}/plans/{pid}/confirm", headers=_auth(host),
                            json={"option_id": opt, "headcount": 10})
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "booked"


# --- Resolution idempotency + deadline validation --------------------------


def test_resolution_is_idempotent(client: TestClient, db: Session, flag_on: None) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    _build_open_plan(client, host, package_id, slots)
    when = datetime.now(UTC) + timedelta(days=3)
    assert _resolve(db, when) == 1
    assert _resolve(db, when) == 0  # already resolved


def test_deadline_too_close_to_slot_rejected(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host, days_out=1)  # slot ~1 day out
    plan = client.post(f"{PREFIX}/plans", headers=_auth(host), json={}).json()
    pid = plan["id"]
    client.post(f"{PREFIX}/plans/{pid}/options/package", headers=_auth(host),
                json={"package_id": package_id, "slot_id": slots[0]})
    # Deadline 12h out but slot only ~24h out → inside the 24h min gap.
    deadline = (datetime.now(UTC) + timedelta(hours=12)).isoformat()
    resp = client.put(f"{PREFIX}/plans/{pid}/deadline", headers=_auth(host),
                      json={"deadline_at": deadline})
    assert resp.status_code == 409


def test_cannot_open_without_package_option(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    plan = client.post(f"{PREFIX}/plans", headers=_auth(host), json={}).json()
    pid = plan["id"]
    client.post(f"{PREFIX}/plans/{pid}/options/custom", headers=_auth(host),
                json={"text": "Just a backyard party"})
    resp = client.post(f"{PREFIX}/plans/{pid}/open", headers=_auth(host))
    assert resp.status_code == 409  # need >=2 options incl a package


# --- Privacy: anonymity, no child PII, consent survival --------------------


def test_vote_is_anonymous_no_endpoint_leaks_choice(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv = _rsvp(client, token)
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    client.post(f"{PREFIX}/plans/{pid}/invites/{view['invites'][0]['id']}/approve",
                headers=_auth(host))
    opt = next(o["id"] for o in view["options"] if o["kind"] == "package")
    client.put(f"{PREFIX}/invite/{inv}/vote", json={"option_id": opt})

    # Host view: invites carry no vote / option reference.
    hv = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    assert all("option" not in str(k).lower() for k in hv["invites"][0])
    # Invitee self-view: has_voted boolean only, never which option.
    self_view = client.get(f"{PREFIX}/invite/{inv}").json()
    assert self_view["has_voted"] is True
    assert "option_id" not in self_view and "vote" not in {k.lower() for k in self_view}


def test_no_child_fields_in_any_response(client: TestClient, db: Session, flag_on: None) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv = _rsvp(client, token)
    blobs = [
        client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).text,
        client.get(f"{PREFIX}/public/{token}").text,
        client.get(f"{PREFIX}/invite/{inv}").text,
    ]
    for blob in blobs:
        low = blob.lower()
        assert "date_of_birth" not in low and "dob" not in low
        assert "medical" not in low and "child" not in low


def test_marketing_consent_stored_separately(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    token = opened["share_token"]
    email = "consenting@example.com"
    client.post(f"{PREFIX}/public/{token}/rsvp", json={
        "parent_name": "Jo", "email": email, "attending": True, "kid_count": 2,
        "marketing_opt_in": True,
    })
    consent = db.scalar(
        select(PlanMarketingConsent).where(PlanMarketingConsent.email == email)
    )
    assert consent is not None and consent.source == "party_planner_rsvp"


# --- Abuse: honeypot, rate limit, no enumeration ---------------------------


def test_honeypot_silently_drops(client: TestClient, db: Session, flag_on: None) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    resp = client.post(f"{PREFIX}/public/{token}/rsvp", json={
        "parent_name": "Bot", "email": "bot@example.com", "attending": True,
        "kid_count": 1, "website": "http://spam.example",
    })
    assert resp.status_code == 201  # looks successful
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    assert view["invites"] == []  # nothing persisted


def test_rate_limit_blocks_flood(client: TestClient, db: Session, flag_on: None) -> None:
    config_service.set_value(
        db, key=config_service.KEY_PARTY_PLANNER_RSVP_RATE_PER_HOUR, value=2, changed_by_id=None
    )
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    token = opened["share_token"]
    codes = [
        client.post(f"{PREFIX}/public/{token}/rsvp", json={
            "parent_name": "G", "email": f"g{i}@example.com", "attending": True, "kid_count": 1,
        }).status_code
        for i in range(3)
    ]
    assert codes[0] == 201 and codes[1] == 201 and codes[2] == 429


def test_unknown_tokens_are_indistinguishable_404(
    client: TestClient, db: Session, flag_on: None
) -> None:
    assert client.get(f"{PREFIX}/public/does-not-exist").status_code == 404
    assert client.get(f"{PREFIX}/invite/does-not-exist").status_code == 404


def test_blocked_invitee_cannot_edit_rsvp(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv = _rsvp(client, token)
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    client.post(f"{PREFIX}/plans/{pid}/invites/{view['invites'][0]['id']}/block",
                headers=_auth(host))
    resp = client.put(f"{PREFIX}/invite/{inv}/rsvp",
                      json={"attending": True, "kid_count": 9})
    assert resp.status_code == 409  # opaque; no "you're blocked" oracle


def test_html_and_urls_stripped_from_public_text(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    plan = client.post(f"{PREFIX}/plans", headers=_auth(host), json={}).json()
    pid = plan["id"]
    client.post(f"{PREFIX}/plans/{pid}/options/custom", headers=_auth(host),
                json={"text": "<img src=x onerror=alert(1)> visit http://evil.example now"})
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    custom = next(o for o in view["options"] if o["kind"] == "custom")
    assert "<" not in custom["custom_text"] and "http" not in custom["custom_text"]


# --- Milestone C: theme + reactions ----------------------------------------


def test_set_theme_and_reject_unknown(client: TestClient, db: Session, flag_on: None) -> None:
    host = _signup(client)
    plan = client.post(f"{PREFIX}/plans", headers=_auth(host), json={}).json()
    pid = plan["id"]
    ok = client.put(f"{PREFIX}/plans/{pid}/theme", headers=_auth(host), json={"theme": "dino"})
    assert ok.status_code == 200 and ok.json()["theme"] == "dino"
    bad = client.put(f"{PREFIX}/plans/{pid}/theme", headers=_auth(host), json={"theme": "hacker"})
    assert bad.status_code == 400


def test_emoji_reaction_toggles_and_aggregates(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv = _rsvp(client, token)
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    client.post(f"{PREFIX}/plans/{pid}/invites/{view['invites'][0]['id']}/approve",
                headers=_auth(host))
    opt = next(o["id"] for o in view["options"] if o["kind"] == "package")

    # React → count 1.
    client.put(f"{PREFIX}/invite/{inv}/react", json={"option_id": opt, "emoji": "🎉"})
    pub = client.get(f"{PREFIX}/public/{token}").json()
    assert next(o for o in pub["options"] if o["id"] == opt)["reactions"].get("🎉") == 1
    # Tap again → toggles off.
    client.put(f"{PREFIX}/invite/{inv}/react", json={"option_id": opt, "emoji": "🎉"})
    pub = client.get(f"{PREFIX}/public/{token}").json()
    assert "🎉" not in next(o for o in pub["options"] if o["id"] == opt)["reactions"]


def test_reaction_rejects_unknown_emoji(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv = _rsvp(client, token)
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    client.post(f"{PREFIX}/plans/{pid}/invites/{view['invites'][0]['id']}/approve",
                headers=_auth(host))
    opt = next(o["id"] for o in view["options"] if o["kind"] == "package")
    resp = client.put(f"{PREFIX}/invite/{inv}/react", json={"option_id": opt, "emoji": "💣"})
    assert resp.status_code == 400


# --- Milestone D: lifecycle notifications + purge --------------------------


def _approve_and_vote(client: TestClient, pid: str, token: str, host: str, *,
                      email: str) -> tuple[str, str]:
    """RSVP a guest, approve them, vote the first package option. Returns (invite_token, opt)."""
    inv = _rsvp(client, token, email=email)
    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    client.post(f"{PREFIX}/plans/{pid}/invites/{view['invites'][0]['id']}/approve",
                headers=_auth(host))
    opt = next(o["id"] for o in view["options"] if o["kind"] == "package")
    client.put(f"{PREFIX}/invite/{inv}/vote", json={"option_id": opt})
    return inv, opt


def test_reveal_emailed_to_approved_invitees(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    _approve_and_vote(client, pid, token, host, email="reveal-guest@example.com")

    later = datetime.now(UTC) + timedelta(days=3)
    gw = FakeEmailGateway()
    planner_service.resolve_due_plans(db, now=later, email_gateway=gw)
    assert any(m["to"] == "reveal-guest@example.com" and "decided" in (m["subject"] or "").lower()
               for m in gw.outbox)
    # Idempotent — a second resolve pass doesn't re-announce.
    gw2 = FakeEmailGateway()
    planner_service.resolve_due_plans(db, now=later, email_gateway=gw2)
    assert gw2.outbox == []


def test_override_emails_change_of_plans(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    _inv, winner_opt = _approve_and_vote(client, pid, token, host, email="chg@example.com")
    planner_service.resolve_due_plans(db, now=datetime.now(UTC) + timedelta(days=3))

    view = client.get(f"{PREFIX}/plans/{pid}", headers=_auth(host)).json()
    other_opt = next(o["id"] for o in view["options"]
                     if o["kind"] == "package" and o["id"] != winner_opt)
    host_id = db.get(PartyPlan, uuid.UUID(pid)).host_user_id  # type: ignore[union-attr]
    gw = FakeEmailGateway()
    planner_service.confirm_booking(
        db, plan_id=uuid.UUID(pid), actor_id=host_id, gateway=FakeGateway(),
        option_id=uuid.UUID(other_opt), headcount=10, email_gateway=gw,
    )
    assert any(m["to"] == "chg@example.com" and "change of plans" in (m["subject"] or "").lower()
               for m in gw.outbox)


def test_low_rsvp_nudge_fires_once(client: TestClient, db: Session, flag_on: None) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)  # deadline +2 days, 0 RSVPs
    _ = opened
    within_24h = datetime.now(UTC) + timedelta(days=2) - timedelta(hours=12)
    gw = FakeEmailGateway()
    low, _rev = planner_service.send_planner_nudges(db, now=within_24h, email_gateway=gw)
    assert low == 1 and any("RSVP" in (m["subject"] or "") for m in gw.outbox)
    # Marker set → no repeat.
    gw2 = FakeEmailGateway()
    low2, _ = planner_service.send_planner_nudges(db, now=within_24h, email_gateway=gw2)
    assert low2 == 0


def test_revote_nudge_emails_voters_of_removed_option(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    _inv, opt = _approve_and_vote(client, pid, token, host, email="voter@example.com")
    client.request("DELETE", f"{PREFIX}/plans/{pid}/options/{opt}", headers=_auth(host))

    gw = FakeEmailGateway()
    _low, revote = planner_service.send_planner_nudges(db, now=datetime.now(UTC), email_gateway=gw)
    assert revote == 1
    assert any(m["to"] == "voter@example.com" and "re-vote" in (m["subject"] or "").lower()
               for m in gw.outbox)


def test_purge_anonymises_pii_but_keeps_vote_counts(
    client: TestClient, db: Session, flag_on: None
) -> None:
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)  # slot ~12 days out
    opened = _build_open_plan(client, host, package_id, slots)
    pid, token = opened["id"], opened["share_token"]
    inv, _opt = _approve_and_vote(client, pid, token, host, email="purge-me@example.com")
    _ = inv
    planner_service.resolve_due_plans(db, now=datetime.now(UTC) + timedelta(days=3))
    client.post(f"{PREFIX}/plans/{pid}/confirm", headers=_auth(host), json={"headcount": 10})

    votes_before = db.scalar(select(func.count()).select_from(PlanVote))
    # Well past the event date + purge horizon (30 days).
    purged = planner_service.purge_expired_plan_pii(db, now=datetime.now(UTC) + timedelta(days=60))
    assert purged >= 1
    invite = db.scalar(select(PlanInvite).where(PlanInvite.plan_id == uuid.UUID(pid)))
    assert invite is not None and invite.email == "" and invite.parent_name == "(removed)"
    plan = db.get(PartyPlan, uuid.UUID(pid))
    assert plan is not None and plan.purged_at is not None
    # Aggregate vote counts survive the PII purge (anonymise-in-place).
    assert db.scalar(select(func.count()).select_from(PlanVote)) == votes_before


def test_abandoned_draft_with_invites_still_purges(
    client: TestClient, db: Session, flag_on: None
) -> None:
    # A slot-less draft (host emailed invites then abandoned it) must not retain PII forever (B1).
    host = _signup(client)
    plan = client.post(f"{PREFIX}/plans", headers=_auth(host), json={}).json()
    pid = plan["id"]
    client.post(f"{PREFIX}/plans/{pid}/invites", headers=_auth(host),
                json={"invites": [{"email": "abandoned@example.com", "name": "Sam"}]})
    purged = planner_service.purge_expired_plan_pii(db, now=datetime.now(UTC) + timedelta(days=60))
    assert purged >= 1
    invite = db.scalar(select(PlanInvite).where(PlanInvite.plan_id == uuid.UUID(pid)))
    assert invite is not None and invite.email == ""
    # The guest address is also scrubbed from the transactional planner delivery log (S1).
    remaining = db.scalar(
        select(func.count()).select_from(NotificationLog)
        .where(NotificationLog.to_email == "abandoned@example.com")
    )
    assert remaining == 0


def test_low_rsvp_nudge_counts_actual_responders_not_email_invites(
    client: TestClient, db: Session, flag_on: None
) -> None:
    # Pre-approved email invites must not mask a silent room (S2).
    host = _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    pid = opened["id"]
    client.post(f"{PREFIX}/plans/{pid}/invites", headers=_auth(host), json={"invites": [
        {"email": f"g{i}@example.com", "name": "G"} for i in range(6)
    ]})  # 6 approved invites, but zero RSVPs
    within_24h = datetime.now(UTC) + timedelta(days=2) - timedelta(hours=12)
    gw = FakeEmailGateway()
    low, _rev = planner_service.send_planner_nudges(db, now=within_24h, email_gateway=gw)
    assert low == 1  # fires despite 6 approved email invites, because nobody RSVP'd


def test_non_host_cannot_view_plan(client: TestClient, db: Session, flag_on: None) -> None:
    host, other = _signup(client), _signup(client)
    package_id, slots = _package_with_slots(client, host)
    opened = _build_open_plan(client, host, package_id, slots)
    resp = client.get(f"{PREFIX}/plans/{opened['id']}", headers=_auth(other))
    assert resp.status_code == 403
