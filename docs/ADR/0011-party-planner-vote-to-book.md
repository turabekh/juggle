# ADR 0011 — Party Planner: vote-to-book birthday planning (decision set)

- Status: **ACCEPTED** (Turaboy, 2026-07-12) — Milestone A next; B–D follow in sequence
- Date: 2026-07-12
- Invariants touched: INV-1, INV-2, INV-3, INV-11, INV-12, INV-13
- Related: ADR-0006 (re-gate, G2 in active gate), ADR-0007/0008/0010 (party money);
  PRD §9 (parties), §10.1 (config), §11 (child data); PRD-EXT-1 §3-G2, §5 (INV-12/13),
  §7 (data model), §8 (metrics), §10 (non-goals: *no public rosters or attendee visibility*)
- Supersedes: the G2 spec as "invites + RSVP" (PRD-EXT-1 §3-G2) — G2 **evolves** into
  "Party Planner (invites + vote-to-book)". No change to the parties money model (ADR-0007/0008/0010)
  or the payments track (F-PAY); the planner is a layer *on top of* `PartyBooking`.

## Context

G2 (party invites + RSVP) is in the active build gate (ADR-0006), shipping with the parties
vertical. Rather than a plain invite/RSVP, we build a **Party Planner**: a host picks up to 4 party
options, invitees RSVP + vote via a shareable link, and at a deadline the plan **resolves** into a
winner announcement and — for package winners — a one-tap booking through the **existing** parties +
payments rails. The RSVP page is Juggle's highest-value acquisition surface (every invited parent is
a warm, non-user lead), so the planner is also the growth flywheel (PRD-EXT-1 §8 north-star).

This is a **planning layer only**. It creates no holds, moves no money itself, and adds no new money
code — at resolution it hands off to the existing `parties.service.book_slot` deposit flow (INV-2).

## LOCKED DECISIONS (recorded verbatim; the design conforms to these)

- **Invites:** hybrid — open shareable link + optional per-guest email invites. Open-link RSVP
  captures parent name + email (transactional-only); host approval of open-link RSVPs defaults ON;
  link token ≥128-bit opaque, noindex, expires at deadline.
- **Child data:** two-stage minimal. RSVP = parent name/email + attending-kid count + optional
  nickname/avatar. Child first name + dietary/allergy collected only post-resolution from confirmed
  "yes" guests, via the existing booking detail flow; no guest-kid DOB or surname, ever; roster
  visible to host + provider only; invitees never see each other's kids' data.
- **Inventory/money:** votes are non-binding on inventory; no holds, no deposits during voting;
  options display live availability (INV-12 real numbers); at resolution the host confirms the
  winner manually (runner-up fallback if sold out). Auto-book with pre-consented deposit is OUT
  (fast-follow).
- **Options:** up to 4 total = Juggle party packages (each option carries its specific slot datetime
  — the vote is implicitly a date vote; render that clearly) + max 1 custom free-text option. Custom
  winner still gets full reveal flow + "book something similar" nudge; custom options are never
  deposit-bookable.
- **Gamification honesty:** votes anonymous to EVERYONE including host and admin surfaces (tallies
  only; no API endpoint may return vote-by-invite; the vote row references the invite solely for
  one-vote enforcement); RSVP attendance visible as nickname/avatar board; "⭐ birthday kid's
  favourite" badge = host's child ranks options at plan creation, badge shown on their top pick.
- **Hard dependency:** real email gateway must land before any live family uses this. Feature ships
  behind flag `party_planner` (flags module), OFF in production until email is real.

## RESOLVED EDGES (recorded verbatim; adopted — no blockers found, see reconciliations below)

1. One vote per invite (per parent-email/token), regardless of kid count; kid count feeds
   headcount/pricing only.
2. Invitees may edit RSVP and vote freely until the deadline.
3. No quorum. T-24h before deadline, if RSVPs < a config threshold, host gets a low-participation
   nudge with one-tap 48h extend (extend allowed while deadline validation still passes). At deadline
   the plan resolves regardless.
4. Reveal mechanics: at deadline the winner is announced to all invitees automatically (information,
   not a booking); the host is simultaneously prompted to confirm the booking, and may override — an
   override sends a "change of plans" update notice to all. Tie-break: birthday-kid ranking wins among
   tied options; if still tied, reveal says "It's a tie — host is choosing!" and host picks at
   confirmation.
5. Deadline validation: hard-fail if deadline ≥ earliest option slot start minus a config minimum gap
   (default 24h); warn (not block) if deadline lands inside the T-7d balance or T-72h adjustment
   windows of any option.
6. Mid-vote sell-out / option swap: host may add/remove/replace options while the plan is open; votes
   on a removed option are voided and those voters get a re-vote nudge.
7. Retention: guest parent emails, nicknames, avatars, and post-resolution child details auto-purge N
   days after the event date (default 30, config-bounded); aggregate counts persist PII-free;
   RSVP-time marketing opt-ins survive the purge in the marketing list only (separate consent, Spam
   Act).
8. Custom-option text: length-capped, URL-stripped, profanity-filtered (renders on a public page —
   treat as untrusted).

## Reconciliations surfaced (per house rules — don't silently deviate)

- **EXT-1 §10 "No public rosters or attendee visibility" vs the who's-in board.** These are
  reconciled, not violated: the board is (a) **audience-scoped** behind the opaque, noindex,
  deadline-expiring token — never public or search-indexable; (b) **pseudonymous** — parent-chosen
  nickname + avatar only, never a child identity and never contact data; (c) **not a roster** — it
  carries zero kid data. It is strictly weaker than G2's own "kids' names visible only within the
  invite audience" (we show no kid identities at all). The actual roster (child first name + dietary)
  stays host + provider only (INV-3). The ADR asserts this explicitly so the constraint is a design
  input, not an afterthought.
- **Marketing opt-in (edge 7) with no marketing infrastructure yet.** The RSVP marketing opt-in is
  recorded as a **store-only consent record** (email + consent flag + source + timestamp), strictly
  separate from the transactional guest record, and is **exempt from the purge**. There is no
  marketing *send* path today; downstream use is deferred until a marketing capability exists. We
  capture consent correctly now (Spam Act discipline, INV-13) without building send infra in scope.

## Placement (the ADR note the task requested)

**New `party_planner` module**, inserted in the import-linter layering **immediately above
`parties`** (i.e. `… booking ▸ party_planner ▸ parties ▸ payments …`). Rationale:

- The planner is a layer *on top of* `PartyBooking`; it imports `parties.service` (for the
  vote-to-book hand-off and live availability), plus the low utilities `notifications`, `config`,
  `flags`, `events`, `audit`. All are **below** it — contracts stay KEPT.
- It owns a **public, unauthenticated, tokenized surface** with its own abuse controls (rate limits,
  honeypot, approval queue, token expiry). Isolating that in its own module keeps the untrusted
  surface out of the authenticated `parties` CRUD.
- The **scheduler** (top of the layering) gains a resolution + purge step calling
  `party_planner.service.resolve_due_plans()` / `purge_expired_plan_pii()` on the existing tick.
- Rejected alternative — folding into `parties`: parties would absorb an unrelated public/untrusted
  concern and grow a second, very different bounded context. The layer boundary is cleaner as its own
  module.

## State machine

`draft → open → resolved → (booked | expired_unbooked)`

- **draft** — host is assembling options/deadline; not shareable.
- **open** — link live; RSVP + vote + edit-until-deadline permitted; host may swap options / extend.
- **resolved** — deadline passed; winner computed + announced (idempotent scheduler job); awaiting
  host action.
- **booked** — host confirmed a **package** winner → an existing `PartyBooking` created via
  `parties.service.book_slot` (headcount prefilled from "yes" RSVPs); `plan.booking_id` set.
- **expired_unbooked** — custom-option winner, or host never books; terminal. PII still purges per
  edge 7.

Transitions and one-vote/edit-until-deadline are enforced at the **DB layer** where possible:
`UNIQUE(plan_invite_id)` on `plan_vote` (one vote per invite; edit = update in place); votes/RSVP
writes rejected in the service unless `plan.status = open` and `now < deadline`.

## Data model deltas (PRD-EXT-1 §7)

`party_plan` (host_user_id, status, deadline_at, event_date, theme, birthday_kid_ranking JSON,
token opaque ≥128-bit UNIQUE, approval_required bool, booking_id FK→party_booking nullable,
resolved_at, purged_at nullable) · `plan_option` (plan_id, kind[package|custom], package_id +
slot_id nullable for package, custom_text nullable, position, voided bool) · `plan_invite` (plan_id,
mode[open|email], email, parent_name, status[pending|approved|removed], token, marketing_opt_in bool)
· `plan_rsvp` (plan_invite_id, attending bool, kid_count, nickname, avatar_key) · `plan_vote`
(plan_id, plan_invite_id UNIQUE, plan_option_id). No child columns anywhere in the planner; the
post-resolution roster lives on the resulting `PartyBooking` (INV-3).

## Config knobs (INV-11 — all typed, bounded, versioned, audit-logged via `config.REGISTRY`)

- `party_planner_max_options` (default 4, bounds 2–4)
- `party_planner_min_deadline_gap_hours` (default 24, bounds 1–168) — edge 5 hard-fail gap
- `party_planner_low_rsvp_threshold` (default 5, bounds 0–100) — edge 3 nudge trigger
- `party_planner_extend_hours` (default 48, bounds 1–168) — edge 3 one-tap extend
- `party_planner_purge_days` (default 30, bounds 1–365) — edge 7 PII purge horizon
- `party_planner_rsvp_rate_per_hour` (default 20, bounds 1–1000) — per-IP + per-token RSVP/vote cap
- `party_planner_custom_option_maxlen` (default 80, bounds 10–200) — edge 8 length cap

## Flag (flags module)

`party_planner` — default **OFF in production** until the real email gateway lands. All planner
routers/UX gate on it. Dev/test may enable it (FakeEmailGateway) to build + e2e.

## Invariants in play (with how each is respected + tested)

- **INV-1** — the planner never creates holds; only a host *booking confirmation* touches inventory,
  via the unchanged `parties.service.book_slot` path. Test: resolution + confirm creates exactly one
  `PartyBooking`/deposit and no holds appear during the open phase.
- **INV-2** — no new money code; deposit/booking is a link-through to F-PAY rails. Test: no `payments`
  writes occur until host confirm; the confirm reuses the existing deposit PaymentIntent flow.
- **INV-3** — guest-child data = first name + dietary only, post-resolution, on the booking; no
  guest-kid DOB/surname; roster host+provider only. Test: no planner endpoint returns any child field;
  no child column exists in planner tables.
- **INV-11** — every knob above is a bounded `config` spec; no hardcoded planner constants. Test:
  out-of-bounds rejected; resolution/nudge read from config.
- **INV-12** — every countdown, tally, availability, and readiness number is real (live inventory
  projection + true vote counts). Test: tallies equal actual votes; availability equals the live
  projection; no synthetic values.
- **INV-13** — no child PII in URLs/params/analytics/share copy; token pages `noindex`; guest emails
  transactional-only with separate marketing consent; purge policy enforced. Test: token is opaque
  and child-free; analytics events carry no child fields; purge job removes guest PII, aggregates
  remain (clock-controlled).

## Abuse & safety (public unauthenticated surface — security-scanner mandatory before merge)

Per-IP + per-token rate limits on RSVP/vote (`party_planner_rsvp_rate_per_hour`); host approval queue
with remove + block; honeypot field on open-link RSVP; token expiry at deadline; **no enumeration** —
invalid, expired, and not-found token pages are indistinguishable (same generic 404/410 response,
no timing/message oracle); custom-option text length-capped + URL-stripped + profanity-filtered
(edge 8). The purge job is itself security-reviewed (edge 7).

## Consequences

- **Growth flywheel** (PRD-EXT-1 §8 north-star): every party pushes ~10–15 warm parent leads through
  a branded, delightful moment with an attributed "plan your own" CTA.
- **No money-model risk:** the planner adds zero money code; all deposits/refunds stay in F-PAY. The
  only new mutation touching inventory is the host's manual confirm, reusing `book_slot`.
- **New public attack surface** — mitigated by the abuse controls above; gated OFF in prod behind the
  flag until email + a security pass are done.
- **Metrics** (PRD-EXT-1 §8): plan→booking conversion (≥40% of resolved plans with a package winner),
  RSVPs per plan (≥10), invitee→signup within 60d (≥10%).

## Alternatives considered

- **Plain G2 invite/RSVP (no vote).** Rejected: the vote is the engagement/virality mechanic and the
  reason invitees return to the page (multiple sessions per invitee), and it doubles as the date +
  headcount decision. The plain version is strictly less of the funnel.
- **Auto-book the winner at deadline (pre-consented deposit).** Deferred to a fast-follow (LOCKED):
  it needs pre-authorised max-deposit consent + a failure story; manual host confirm is safer for v1
  and keeps INV-1/INV-5 reasoning simple.
- **Fold planner into `parties`.** Rejected — see Placement; mixing an untrusted public surface into
  authenticated CRUD is the wrong boundary.
- **Bind inventory during voting (hold the option slots).** Rejected — holding up to 4 capacity-1
  slots (and/or deposits) hostage during a multi-day vote strands inventory and complicates INV-1;
  non-binding + live availability + runner-up fallback is honest and simpler.

## Sequencing & workflow (informative — build begins only on acceptance)

A (core model + API) → B (surfaces) → C (gamified layer) → D (lifecycle + notifications), branch/PR
per milestone. plan-critic before A (state machine + PII surface); security-scanner on all public
endpoints + the purge job; migration-guard per migration; integration tests on resolution, tie-break,
option-swap re-vote, approval queue, purge; Playwright e2e per the task DoD; all behind the
`party_planner` flag (default OFF). Never push without asking; handoff per session.

## Dependencies

- Builds on the shipped parties money model (ADR-0007/0008/0010) + F-PAY rails — all complete.
- **Real email gateway** is a hard go-live dependency (flag stays OFF in prod until it lands).
- Step-0 doc amendments (below) merge with this ADR's acceptance:
  PRD-EXT-1 §3-G2 (rewrite), §7 (planner entities), §8 (planner metrics); CLAUDE.md gate matrix G2
  wording; ADR README index row.
