"""Planner composer gateway — mirrors the payment/email/SMS gateway pattern.

The planner depends on a ``PlannerGateway`` Protocol, not on any LLM. A
``RuleBasedPlannerGateway`` (deterministic day-packing) backs dev/tests and is
the fallback whenever the LLM is unconfigured or errors; an
``AnthropicPlannerGateway`` (Claude) drops in behind the same interface when
``JUGGLE_ANTHROPIC_API_KEY`` is set.

INV-3: the brief carries child *ages* only, and candidates are public listing
data — no child name/DOB/medical ever reaches the model.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from zoneinfo import ZoneInfo

from juggle.modules.planner.core.schemas import (
    CandidateSession,
    PlanDraft,
    PlanDraftItem,
    PlanRequest,
)
from juggle.settings import get_settings

_PERTH = ZoneInfo("Australia/Perth")  # WA has no DST (INV-7) — group by local day


class PlannerGateway(Protocol):
    def compose(self, request: PlanRequest, candidates: list[CandidateSession]) -> PlanDraft: ...


# --- deterministic rule-based composer (no LLM) ------------------------------


def _age_fits(age: int, cand: CandidateSession) -> bool:
    return cand.age_min <= age <= cand.age_max


def _score(request: PlanRequest, cand: CandidateSession) -> float:
    """Higher is better: age fit + interest match + cheaper + closer + in stock."""
    fits = [a for a in request.ages if _age_fits(a, cand)]
    if not fits:
        return -1.0
    score = 10.0 * len(fits)
    if request.categories and cand.category in request.categories:
        score += 8.0
    if cand.distance_km is not None:
        score += max(0.0, 5.0 - cand.distance_km / 5.0)
    # Cheaper is gently preferred; seats give a small nudge (never fabricate scarcity).
    score += max(0.0, 3.0 - cand.price_cents / 5000.0)
    score += min(2.0, cand.seats_remaining * 0.1)
    return score


@dataclass
class RuleBasedPlannerGateway:
    """Greedy day-packing: best-scoring, non-overlapping picks within budget."""

    max_days: int = 5

    def compose(self, request: PlanRequest, candidates: list[CandidateSession]) -> PlanDraft:
        ranked = sorted(
            (c for c in candidates if _score(request, c) >= 0),
            key=lambda c: _score(request, c),
            reverse=True,
        )
        picked: list[PlanDraftItem] = []
        used_days: set[date] = set()
        used_programs: set[uuid.UUID] = set()
        spent = 0
        # Two passes: first fill each day with a *different* activity (variety);
        # then, only if days remain empty, allow repeating an activity to fill them.
        for allow_repeat in (False, True):
            for cand in ranked:
                if len(picked) >= self.max_days:
                    break
                day = cand.starts_at.astimezone(_PERTH).date()  # local day (INV-7)
                if day in used_days:  # one activity per day keeps the plan uncluttered
                    continue
                if not allow_repeat and cand.program_id in used_programs:
                    continue  # already have this activity — prefer something new
                if (
                    request.budget_cents is not None
                    and spent + cand.price_cents > request.budget_cents
                ):
                    continue
                fits = [a for a in request.ages if _age_fits(a, cand)]
                picked.append(
                    PlanDraftItem(
                        session_id=cand.session_id,
                        for_ages=fits,
                        reason=f"{cand.category.title()} at {cand.venue_name} — a good fit for "
                        f"age {', '.join(str(a) for a in fits)}.",
                    )
                )
                used_days.add(day)
                used_programs.add(cand.program_id)
                spent += cand.price_cents

        if picked:
            summary = (
                f"A {len(picked)}-day plan for the holidays"
                + (f", around ${spent / 100:,.0f} total." if spent else ".")
            )
        else:
            summary = "No sessions matched those dates and filters — try widening the date range."
        return PlanDraft(items=picked, summary=summary)


# --- Claude composer ---------------------------------------------------------

_SYSTEM = (
    "You are a helpful assistant that plans a school-holiday activity itinerary for a "
    "parent, choosing ONLY from a provided list of real, bookable sessions. Never invent "
    "sessions. Select a set that fits the children's AGES, stays within budget, and avoids "
    "two sessions overlapping in time (prefer at most one per day). Prefer a VARIETY of "
    "different activities across the days — avoid booking the same activity two days running "
    "unless there is genuinely nothing else that fits. For each pick give a "
    "short, warm one-line reason. Then write a friendly 1-2 sentence summary. Refer to "
    "children only by age — you are given ages, never names."
)


@dataclass
class AnthropicPlannerGateway:
    """Claude composes the itinerary from the candidate set. Falls back to the
    deterministic gateway on any error (unconfigured, API failure, refusal,
    or a response that doesn't validate)."""

    api_key: str
    model: str
    fallback: RuleBasedPlannerGateway

    def compose(self, request: PlanRequest, candidates: list[CandidateSession]) -> PlanDraft:
        try:
            return self._compose_ai(request, candidates)
        except Exception:  # noqa: BLE001 — any failure degrades to deterministic planning
            return self.fallback.compose(request, candidates)

    def _compose_ai(
        self, request: PlanRequest, candidates: list[CandidateSession]
    ) -> PlanDraft:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        brief = {
            "children_ages": request.ages,  # ages only — never names/DOB (INV-3)
            "dates": f"{request.date_from.isoformat()} to {request.date_to.isoformat()}",
            "budget_dollars": None if request.budget_cents is None else request.budget_cents / 100,
            "interests": request.categories or "any",
        }
        catalogue = [
            {
                "session_id": str(c.session_id),
                "title": c.title,
                "category": c.category,
                "provider": c.organisation_name,
                "venue": c.venue_name,
                "suburb": c.suburb,
                "when": c.starts_at.strftime("%a %d %b %I:%M%p"),
                "ages": f"{c.age_min}-{c.age_max}",
                "price_dollars": c.price_cents / 100,
                "distance_km": c.distance_km,
                "seats_left": c.seats_remaining,
            }
            for c in candidates
        ]
        user = (
            f"Brief:\n{brief}\n\n"
            f"Available sessions (choose only from these, by session_id):\n{catalogue}"
        )
        message = client.messages.parse(
            model=self.model,
            max_tokens=4000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_format=PlanDraft,
        )
        draft = message.parsed_output
        if draft is None:
            raise ValueError("no parsed output")
        return draft


def get_planner_gateway() -> PlannerGateway:
    """Dependency provider: Claude when configured, deterministic otherwise."""
    settings = get_settings()
    rules = RuleBasedPlannerGateway()
    if settings.anthropic_api_key:
        return AnthropicPlannerGateway(
            api_key=settings.anthropic_api_key, model=settings.anthropic_model, fallback=rules
        )
    return rules
