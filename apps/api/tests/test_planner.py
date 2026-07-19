"""AI holiday planner: live-candidate retrieval, composer validation, INV-3, gating."""

import sys
import types
import uuid
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from juggle.modules.flags.core import service as flags_service
from juggle.modules.planner.core import service
from juggle.modules.planner.core.gateway import (
    AnthropicPlannerGateway,
    RuleBasedPlannerGateway,
)
from juggle.modules.planner.core.schemas import (
    CandidateSession,
    PlanDraft,
    PlanDraftItem,
    PlanRequest,
)

# Future (relative to the seed clock) Perth-morning sessions on distinct days.
MON = ("2026-07-20T01:00:00Z", "2026-07-20T03:00:00Z")
TUE = ("2026-07-21T01:00:00Z", "2026-07-21T03:00:00Z")
WED_A = ("2026-07-22T01:00:00Z", "2026-07-22T03:00:00Z")
WED_B = ("2026-07-22T02:00:00Z", "2026-07-22T04:00:00Z")  # overlaps WED_A


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient) -> str:
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/v1/identity/signup", json={"email": email, "password": "supersecret"}
    ).json()["access_token"]


def _publish(
    client: TestClient,
    token: str,
    *,
    title: str,
    suburb: str,
    category: str = "art",
    price_cents: int = 5000,
    window: tuple[str, str],
) -> str:
    org_id = client.post(
        "/api/v1/org", headers=_auth(token), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(token),
        json={
            "organisation_id": org_id,
            "name": "Venue",
            "suburb": suburb,
            "postcode": "6000",
            "latitude": -31.9523,
            "longitude": 115.8613,
        },
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(token),
        json={"organisation_id": org_id, "title": title, "category": category},
    ).json()["id"]
    starts_at, ends_at = window
    session_id = client.post(
        f"/api/v1/catalog/programs/{program_id}/sessions",
        headers=_auth(token),
        json={
            "venue_id": venue_id,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "capacity": 10,
            "price_cents": price_cents,
            "age_min": 5,
            "age_max": 12,
            "session_type": "full_day",
        },
    ).json()["id"]
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(token))
    return session_id


def _enable(db: Session) -> None:
    flags_service.upsert_flag(db, key="planner", enabled=True, rollout_percentage=100)


def _suburb() -> str:
    # Unique per test so only its own seeded sessions are candidates (isolates
    # the planner from other "Perth" sessions committed to the shared dev DB).
    return f"Testville{uuid.uuid4().hex[:8]}"


def _brief(suburb: str, **over: object) -> PlanRequest:
    base: dict[str, object] = {
        "ages": [8],
        "date_from": date(2026, 7, 20),
        "date_to": date(2026, 7, 25),
        "suburb": suburb,
    }
    base.update(over)
    return PlanRequest(**base)  # type: ignore[arg-type]


class _FakeGateway:
    def __init__(self, draft: PlanDraft) -> None:
        self.draft = draft

    def compose(self, request: PlanRequest, candidates: list) -> PlanDraft:  # noqa: ANN001
        return self.draft


# --- end-to-end (flag-gated HTTP) --------------------------------------------


def test_plan_endpoint_is_flag_gated(client: TestClient) -> None:
    token = _signup(client)
    resp = client.post(
        "/api/v1/planner/plan",
        headers=_auth(token),
        json={"ages": [8], "date_from": "2026-07-20", "date_to": "2026-07-25"},
    )
    assert resp.status_code == 404  # flag off


def test_plan_builds_from_live_sessions(client: TestClient, db: Session) -> None:
    token = _signup(client)
    _enable(db)
    suburb = _suburb()
    s_mon = _publish(client, token, title="Monday Art", suburb=suburb, window=MON)
    s_tue = _publish(
        client, token, title="Tuesday Sport", suburb=suburb, category="sport", window=TUE
    )

    resp = client.post(
        "/api/v1/planner/plan",
        headers=_auth(token),
        json={"ages": [8], "date_from": "2026-07-20", "date_to": "2026-07-25", "suburb": suburb},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = {it["session"]["session_id"] for day in body["days"] for it in day["items"]}
    assert {s_mon, s_tue} <= ids
    assert body["generated_by"] == "rules"
    assert body["total_cents"] == 10000


# --- composer validation (real candidates, controlled draft) -----------------


def test_hallucinated_session_is_dropped(client: TestClient, db: Session) -> None:
    token = _signup(client)
    suburb = _suburb()
    real = _publish(client, token, title="Real", suburb=suburb, window=MON)
    draft = PlanDraft(
        items=[
            PlanDraftItem(session_id=uuid.UUID(real), for_ages=[8], reason="real"),
            PlanDraftItem(session_id=uuid.uuid4(), for_ages=[8], reason="ghost"),
        ],
        summary="x",
    )
    out = service.build_plan(db, request=_brief(suburb), gateway=_FakeGateway(draft))
    ids = {str(it.session.session_id) for day in out.days for it in day.items}
    assert ids == {real}  # the invented session never reaches the parent


def test_overlapping_and_over_budget_picks_are_pruned(client: TestClient, db: Session) -> None:
    token = _signup(client)
    suburb = _suburb()
    a = _publish(client, token, title="Wed A", suburb=suburb, price_cents=4000, window=WED_A)
    b = _publish(client, token, title="Wed B", suburb=suburb, price_cents=4000, window=WED_B)
    draft = PlanDraft(
        items=[
            PlanDraftItem(session_id=uuid.UUID(a), for_ages=[8], reason="a"),
            PlanDraftItem(session_id=uuid.UUID(b), for_ages=[8], reason="b"),
        ],
        summary="x",
    )
    out = service.build_plan(db, request=_brief(suburb), gateway=_FakeGateway(draft))
    picks = [it for day in out.days for it in day.items]
    assert len(picks) == 1  # WED_B overlaps WED_A → one survives

    # Budget below a single session prunes everything.
    broke = service.build_plan(
        db, request=_brief(suburb, budget_cents=100), gateway=_FakeGateway(draft)
    )
    assert broke.total_cents == 0
    assert not [it for day in broke.days for it in day.items]


def _publish_multi(
    client: TestClient,
    token: str,
    *,
    title: str,
    suburb: str,
    windows: list[tuple[str, str]],
    category: str = "art",
) -> tuple[str, list[str]]:
    """One program with several sessions (same program_id) on different days."""
    org_id = client.post(
        "/api/v1/org", headers=_auth(token), json={"name": f"Org {uuid.uuid4().hex[:5]}"}
    ).json()["id"]
    venue_id = client.post(
        "/api/v1/catalog/venues",
        headers=_auth(token),
        json={
            "organisation_id": org_id,
            "name": "Venue",
            "suburb": suburb,
            "postcode": "6000",
            "latitude": -31.9523,
            "longitude": 115.8613,
        },
    ).json()["id"]
    program_id = client.post(
        "/api/v1/catalog/programs",
        headers=_auth(token),
        json={"organisation_id": org_id, "title": title, "category": category},
    ).json()["id"]
    session_ids: list[str] = []
    for starts_at, ends_at in windows:
        sid = client.post(
            f"/api/v1/catalog/programs/{program_id}/sessions",
            headers=_auth(token),
            json={
                "venue_id": venue_id,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "capacity": 10,
                "price_cents": 5000,
                "age_min": 5,
                "age_max": 12,
                "session_type": "full_day",
            },
        ).json()["id"]
        session_ids.append(sid)
    client.post(f"/api/v1/catalog/programs/{program_id}/publish", headers=_auth(token))
    return program_id, session_ids


def test_rule_based_plan_varies_activities_across_days(
    client: TestClient, db: Session
) -> None:
    """The packer must not book the same program every day when an alternative fits."""
    token = _signup(client)
    _enable(db)
    suburb = _suburb()
    # "Repeaty" runs Mon + Tue; "Variety" runs Tue only.
    _publish_multi(client, token, title="Repeaty", suburb=suburb, windows=[MON, TUE])
    _, variety_sessions = _publish_multi(
        client, token, title="Variety", suburb=suburb, windows=[TUE], category="sport"
    )

    out = service.build_plan(db, request=_brief(suburb), gateway=RuleBasedPlannerGateway())
    titles = {it.session.title for day in out.days for it in day.items}
    ids = {str(it.session.session_id) for day in out.days for it in day.items}
    # Tuesday should switch to "Variety" rather than repeat "Repeaty".
    assert titles == {"Repeaty", "Variety"}
    assert variety_sessions[0] in ids


def test_rule_based_gateway_needs_no_llm(client: TestClient, db: Session) -> None:
    token = _signup(client)
    suburb = _suburb()
    _publish(client, token, title="Solo", suburb=suburb, window=MON)
    out = service.build_plan(db, request=_brief(suburb), gateway=RuleBasedPlannerGateway())
    assert out.candidate_count >= 1
    assert out.summary  # deterministic, non-empty


# --- AI composer (Claude) path, exercised via a mocked SDK client ------------


def _candidate(**over: object) -> CandidateSession:
    base: dict[str, object] = dict(
        session_id=uuid.uuid4(),
        program_id=uuid.uuid4(),
        title="Art Camp",
        category="art",
        organisation_name="Org",
        venue_name="Venue",
        suburb="Perth",
        starts_at=datetime(2026, 7, 20, 1, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 3, 0, tzinfo=UTC),
        price_cents=5000,
        age_min=5,
        age_max=12,
        seats_remaining=5,
        distance_km=None,
    )
    base.update(over)
    return CandidateSession(**base)  # type: ignore[arg-type]


def _fake_anthropic(parse_impl: object) -> types.SimpleNamespace:
    class _Messages:
        def parse(self, **kwargs: object) -> object:
            return parse_impl(**kwargs)  # type: ignore[operator]

    class _Client:
        def __init__(self, **_: object) -> None:
            self.messages = _Messages()

    return types.SimpleNamespace(Anthropic=_Client)


def test_anthropic_gateway_composes_from_parsed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cand = _candidate()
    draft = PlanDraft(
        items=[PlanDraftItem(session_id=cand.session_id, for_ages=[8], reason="ai pick")],
        summary="An AI-composed day out.",
    )

    def parse(**kwargs: object) -> object:
        # INV-3: the payload sent to the model must carry no child PII.
        payload = str(kwargs)
        assert "date_of_birth" not in payload
        assert "first_name" not in payload
        assert "medical" not in payload
        return types.SimpleNamespace(parsed_output=draft)

    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(parse))
    gateway = AnthropicPlannerGateway(
        api_key="k", model="claude-opus-4-8", fallback=RuleBasedPlannerGateway()
    )
    result = gateway.compose(
        PlanRequest(ages=[8], date_from=date(2026, 7, 20), date_to=date(2026, 7, 25)), [cand]
    )
    assert result.summary == "An AI-composed day out."
    assert [i.session_id for i in result.items] == [cand.session_id]


def test_anthropic_gateway_falls_back_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cand = _candidate()

    def boom(**_: object) -> object:
        raise RuntimeError("api unavailable")

    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(boom))
    gateway = AnthropicPlannerGateway(
        api_key="k", model="claude-opus-4-8", fallback=RuleBasedPlannerGateway()
    )
    result = gateway.compose(
        PlanRequest(ages=[8], date_from=date(2026, 7, 20), date_to=date(2026, 7, 25)), [cand]
    )
    # Degrades to the deterministic gateway, which still picks the live candidate.
    assert [i.session_id for i in result.items] == [cand.session_id]


# --- INV-3: no child PII surface ---------------------------------------------


def test_planner_request_carries_no_child_pii() -> None:
    forbidden = {"name", "first_name", "child_name", "date_of_birth", "dob", "medical"}
    assert forbidden.isdisjoint(PlanRequest.model_fields)
    from juggle.modules.planner.core.schemas import CandidateSession

    # The composer only ever sees candidate + age data — no child identifiers.
    assert forbidden.isdisjoint(CandidateSession.model_fields)
