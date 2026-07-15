"""Planner service: turn a parent's brief into a bookable itinerary.

Candidates come from the *live* search projection (INV-8: availability shown =
availability true; INV-12: no fabricated scarcity), so every suggested session is
real and bookable. The composer only ever selects from that set — its output is
re-validated against the candidates here, so a hallucinated session can never
reach the parent.
"""

import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from juggle.modules.planner.core.gateway import PlannerGateway
from juggle.modules.planner.core.schemas import (
    CandidateSession,
    PlanDay,
    PlanItem,
    PlanOut,
    PlanRequest,
)
from juggle.modules.search.core import service as search_service

_PERTH = ZoneInfo("Australia/Perth")  # WA has no DST (INV-7)
MAX_CANDIDATES = 40
_WEEKEND = frozenset({5, 6})  # Sat, Sun (Mon=0)
_WEEKDAY = frozenset({0, 1, 2, 3, 4})


def _days_of_week(day_type: str | None) -> frozenset[int] | None:
    if day_type == "weekend":
        return _WEEKEND
    if day_type == "weekday":
        return _WEEKDAY
    return None


def _age_intersects(request: PlanRequest, card: Any) -> bool:
    return any(card.age_min <= age <= card.age_max for age in request.ages)


def _candidates(db: Session, request: PlanRequest) -> list[CandidateSession]:
    kwargs: dict[str, Any] = {
        "suburb": request.suburb,
        "postcode": request.postcode,
        "date_from": request.date_from,
        "date_to": request.date_to,
        "days_of_week": _days_of_week(request.day_type),
        "start_after_local_hour": request.start_after_hour,
        "available_only": True,
        "limit": 80,
    }
    if request.latitude is not None and request.longitude is not None:
        kwargs["lat"] = request.latitude
        kwargs["lng"] = request.longitude
    if request.radius_km is not None:
        kwargs["radius_km"] = request.radius_km

    cards = search_service.search_sessions(db, **kwargs)
    out: list[CandidateSession] = []
    for card in cards:
        if not _age_intersects(request, card):
            continue
        if request.categories and card.category not in request.categories:
            continue
        if request.drop_off_only and not getattr(card, "drop_off", False):
            continue
        out.append(CandidateSession.model_validate(card))
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def build_plan(db: Session, *, request: PlanRequest, gateway: PlannerGateway) -> PlanOut:
    candidates = _candidates(db, request)
    generated_by = type(gateway).__name__.startswith("Anthropic") and "ai" or "rules"

    if not candidates:
        return PlanOut(
            days=[],
            total_cents=0,
            summary="No sessions matched those dates and filters — try widening the "
            "date range or the area.",
            generated_by=generated_by,
            candidate_count=0,
        )

    draft = gateway.compose(request, candidates)
    by_id = {c.session_id: c for c in candidates}

    # Keep only real candidates, in time order, non-overlapping, within budget.
    chosen: list[PlanItem] = []
    last_end: datetime | None = None
    spent = 0
    seen: set[uuid.UUID] = set()
    for item in sorted(
        (i for i in draft.items if i.session_id in by_id and i.session_id not in seen),
        key=lambda i: by_id[i.session_id].starts_at,
    ):
        cand = by_id[item.session_id]
        if last_end is not None and cand.starts_at < last_end:
            continue  # overlaps a session already in the plan
        if request.budget_cents is not None and spent + cand.price_cents > request.budget_cents:
            continue
        seen.add(item.session_id)
        chosen.append(
            PlanItem(session=cand, for_ages=item.for_ages or request.ages, reason=item.reason)
        )
        last_end = cand.ends_at
        spent += cand.price_cents

    days: dict[date, list[PlanItem]] = {}
    for pi in chosen:
        day = pi.session.starts_at.astimezone(_PERTH).date()
        days.setdefault(day, []).append(pi)

    return PlanOut(
        days=[PlanDay(day=d, items=days[d]) for d in sorted(days)],
        total_cents=spent,
        summary=draft.summary,
        generated_by=generated_by,
        candidate_count=len(candidates),
    )
