# Handoff — 2026-07-12 — Party Planner ADR-0011 + Milestone A (core model + API)

## Scope
Step 0 (ADR + docs) **and** Milestone A (backend core model + API) of the **Party Planner**
(G2 evolved — vote-to-book birthday planning). A host picks ≤4 options, invitees RSVP + vote via a
tokenized public link, the plan resolves at a deadline to a winner, and the host confirms a package
winner through the **existing** parties/payments rails. Planning layer only — no new money code.

Branches (stacked, **not pushed**):
- `docs/party-planner-adr` — Step-0 docs (ADR-0011 ACCEPTED + PRD-EXT-1/CLAUDE/README amendments).
- `feat/party-planner-A` — Milestone A backend, off the docs branch.

## Step 0 (committed on `docs/party-planner-adr`)
- **ADR-0011** (ACCEPTED): LOCKED decisions + resolved edges 1–8 verbatim; new `party_planner`
  module above `parties`; state machine; 7 config knobs; `party_planner` flag (OFF in prod until
  real email); per-invariant handling; abuse/safety; **two reconciliations surfaced** — EXT-1 §10
  "no public rosters/attendee visibility" (board is audience-scoped, pseudonymous, not a roster) and
  marketing consent stored detached/purge-exempt.
- PRD-EXT-1 §3-G2 rewrite, §7 entities, §8 metrics; CLAUDE.md gate matrix; ADR README index.

## Milestone A (committed on `feat/party-planner-A`)
- **New `party_planner` module** (core/ui split), layered immediately above `parties` — contracts KEPT.
- **7 tables** (migration `8961ae257aaf`, up/down round-trips clean, enum-drop in downgrade):
  `party_plan, plan_option, plan_invite, plan_rsvp, plan_vote` (`UNIQUE(plan_invite_id)` = one
  editable vote), `plan_marketing_consent` (detached, purge-exempt), `plan_throttle` (rate limiter).
  **No child columns anywhere** (INV-3) — the roster stays on `PartyBooking`.
- **State machine** `draft → open → resolved → (booked | expired_unbooked)`. Transitions +
  resolve + confirm serialise on a **plan-row `FOR UPDATE`** (kills the double-deposit / resolve-vs-
  vote races). `resolve_due_plans` + `sweep_stale_resolved` (reconciles a failed-deposit booked plan
  back to resolved; expires stale ones) wired into the **scheduler tick** — clock-controlled,
  idempotent. Tie-break = birthday-kid ranking; unbreakable tie → host chooses.
- **Public tokenized surface** (no auth): view / open-RSVP / self-view / edit / vote. Honeypot,
  per-IP + per-token rate limits, sanitised untrusted text (HTML+URL strip, profanity mask, length
  cap), preset avatar keys, generic 404 (no enumeration). **Votes anonymous** — no endpoint returns
  vote-by-invite; invitee self-view exposes only `has_voted: bool`.
- **7 bounded config knobs** (INV-11); everything gated behind the `party_planner` flag.

## Review gates run
- **plan-critic** (pre-A): found 15 issues; folded the blockers into the model/service (plan-row
  locking, approved-only headcount vs package band, confirm guards, **separate marketing-consent
  table**, derived event date, nickname sanitation, once-only markers, ≥2-options+≥1-package to open).
- **security-scanner** (pre-commit): validated anonymity, cross-plan authz, double-book prevention,
  INV-1/2/3/12/13. Fixed 3 findings: **socket IP not spoofable XFF** for rate keys; **per-token cap
  on vote + edit** (ADR-mandated, was IP-only); **blocked/removed invitee write gate**; plus HTML-tag
  strip (defense-in-depth).

## Verification
`make check` **252 passed**, mypy strict, ruff, import-linter **2 contracts KEPT**. Migration
up/down/up verified. 22 planner integration tests. Flag OFF by default (routes 404 when off).

## Known gaps / next (Milestones B–D)
- **B (surfaces):** host create/dashboard/approval-queue/confirm UI + parent public plan page
  (10s-poll tally, reveal). Note: the token page must set `noindex`/`X-Robots-Tag` at the frontend
  (backend can't — flagged by the security review).
- **C (gamified):** theme skins, countdown, animated tally, confetti, who's-in board, readiness meter.
- **D (lifecycle + notifications):** invite/reminder/reveal/override/detail-request emails (stub
  gateway now), the **low-RSVP nudge** + **re-vote nudge** (markers `low_rsvp_nudge_sent_at` /
  `revote_nudge_sent_at` already on the model), and the **PII purge job** (edge 7 — `party_planner_
  purge_days`; must also purge the post-resolution child roster on `PartyBooking` via a parties hook,
  and the account-less child-data collection path needs specifying — deferred per the plan-critic).
- Real email gateway is the hard go-live dependency before the flag flips ON in prod.

## Highest-risk thing to pressure-test next
The **resolve-vs-vote boundary** under real concurrency (the plan-row lock is in place but only
single-threaded tests exercise it), and the **purge** correctly reaching child data on `PartyBooking`
when it lands in D.
