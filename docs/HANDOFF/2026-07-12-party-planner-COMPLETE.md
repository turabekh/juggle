# Handoff — 2026-07-12 — Party Planner (ADR-0011) COMPLETE + parties polish

Comprehensive session handoff. Supersedes the per-milestone notes
(`2026-07-12-party-planner-{A,B,C,D}.md`, `2026-07-12-parties-frontend.md`) as the single
read-me-first for this work. **Read `CLAUDE.md` and then this file** before continuing.

---

## 1. TL;DR

Built the **Party Planner** end to end (ADR-0011, A→B→C→D): a host picks up to 4 party options,
invitees RSVP + vote via a shareable link, the plan resolves at a deadline into a winner + a one-tap
booking through the **existing** parties/payments rails. It is a **planning layer only** — creates no
holds, moves no money itself (INV-1/INV-2). Shipped behind the **`party_planner` feature flag, OFF in
production** until the real email gateway lands.

Alongside it, finished the **parties provider tooling** the planner depends on: full package CRUD
(create/edit/archive/**unarchive**) and a **bulk party-date generator** (date range × weekdays × time
windows) replacing one-slot-at-a-time entry.

**State:** `make check` **267 passed** (32 party_planner + 36 parties tests), mypy strict,
import-linter 2 contracts KEPT; web `vue-tsc` + `vite build` + `vitest` (23) green. All pushed to
`feat/party-planner` (PR #8). **Nothing merged to `main` yet.**

---

## 2. What the feature does (product)

- **Host** (a parent): create a plan → add up to 4 options (Juggle party packages, each carrying a
  specific slot datetime — so a vote is implicitly a **date** vote — plus max 1 custom free-text
  option) → pick a **theme** → set the birthday kid's ⭐ favourite (breaks ties) → set a voting
  deadline → **open** → share the link (or add per-guest email invites).
- **Invitee** (no account): open the tokenized link → RSVP (parent name/email + kid count + optional
  nickname/avatar) → **one editable vote** → live tally / countdown / reactions → **reveal** when it
  closes. Emailed guests land pre-recognised via `?invite=<token>`.
- **Resolution** (scheduler, at the deadline): winner announced to all approved invitees; the host is
  prompted to **confirm** (headcount prefilled from "yes" RSVPs) or **override** (sends a "change of
  plans" notice). Package winners book via the existing deposit flow; custom winners get a "book
  something similar" nudge.
- **Gamified:** theme skins (default/dino/space/unicorn), ticking countdown, confetti on vote,
  animated tally, ⭐ badge, avatar+nickname board, one-tap emoji reactions, host readiness meter.
- **Lifecycle:** transactional emails (invite/RSVP/reveal/change-of-plans/low-RSVP/re-vote nudges);
  guest PII **purged** N days after the event.

---

## 3. Architecture

### Module
New **`party_planner`** module, layered **immediately above `parties`** in the import-linter contract
(`… booking ▸ party_planner ▸ parties ▸ payments …`) — contracts KEPT. It imports `parties`
(vote-to-book hand-off + slot availability), `catalog`/`org` (names), `identity` (host email),
`notifications`, `config`, `flags`, `events`, `audit` — all below it. The **scheduler** (top) drives
resolution / nudges / sweep / purge. Core/ui split; no FastAPI imports in `core/`.

### State machine
`draft → open → resolved → (booked | expired_unbooked)`. Every transition + `resolve` + `confirm`
serialises on a `SELECT … FOR UPDATE` of the `party_plan` row (kills the double-deposit and
resolve-vs-vote races). One-vote + edit-until-deadline enforced at the DB: `UNIQUE(plan_invite_id)`
on `plan_vote`; writes gated on `status=open AND now<deadline`.

### Data model (8 tables, migrations `8961ae257aaf` + `d3ce3e6e6e17`)
`party_plan`, `plan_option`, `plan_invite`, `plan_rsvp`, `plan_vote` (one editable vote/invite),
`plan_reaction` (one-tap emoji, aggregate/unattributed), `plan_marketing_consent` (detached +
**purge-exempt**), `plan_throttle` (rate limiter). **No child columns anywhere** — party bookings are
headcount-only, so there is no per-child roster (INV-3). Once-only markers on the model:
`announced_at`, `low_rsvp_nudge_sent_at`, `revote_nudge_sent_at` (per option), `purged_at`.

### Config (INV-11) — 7 bounded knobs in `config.REGISTRY`
`party_planner_max_options` (4), `_min_deadline_gap_hours` (24), `_low_rsvp_threshold` (5),
`_extend_hours` (48), `_purge_days` (30), `_rsvp_rate_per_hour` (20), `_custom_option_maxlen` (80).

### Flag
`party_planner` — **default OFF in prod**; enabled in `make seed` for local dev/e2e. All routers 404
when off.

### Key API endpoints (`/api/v1/party-planner`)
- **Host (auth):** `POST/GET /plans`, `GET /plans/{id}`, `POST /plans/{id}/options/{package|custom}`,
  `DELETE /plans/{id}/options/{oid}`, `PUT /plans/{id}/{ranking|deadline|theme}`,
  `POST /plans/{id}/{open|extend|confirm}`, `POST /plans/{id}/invites[/{iid}/{approve|remove|block}]`.
- **Public (tokenized, no auth):** `GET /public/{plan_token}`, `POST /public/{plan_token}/rsvp`,
  `GET /invite/{token}`, `PUT /invite/{token}/{rsvp|vote|react}`.

### Frontend (Quasar/Vue)
- Host: `PartyPlansPage` (`/parties/plans`), `PartyPlanManagePage` (`/parties/plans/:id`).
- Public: `PartyPlanRsvpPage` (`/parties/plan/:token`, `noindex`).
- Utils: `lib/planTheme.ts` (CSS-var skins), `lib/confetti.ts` (self-contained), `lib/head.ts` gained
  a `noindex` option. Entry points: "Start a vote" on `PartiesPage`, "Party plans" in the account menu.

---

## 4. Privacy / invariants (how each is respected)

- **INV-1** planner creates no holds; only host `confirm` touches inventory, via unchanged
  `parties.book_slot`.
- **INV-2** no new money code; deposit/booking is a link-through to F-PAY rails.
- **INV-3** no child data in any planner table or endpoint; party bookings are headcount-only.
- **INV-11** all knobs are bounded config specs; no hardcoded planner constants.
- **INV-12** every countdown / tally / availability / readiness number is a real count.
- **INV-13** votes anonymous **by construction** (no endpoint returns vote-by-invite; the invitee
  self-view exposes only `has_voted: bool`; the client remembers its own pick locally). Board is
  pseudonymous (avatar + parent nickname, never a child). Tokens are opaque 256-bit; token page is
  `noindex`. Guest emails are transactional-only; **marketing consent is a detached, purge-exempt
  record**. Reactions are unattributed aggregate counts.
- The **one** place vote→invite is dereferenced is the re-vote nudge — internal only, surfaced on no
  view.

---

## 5. Review gates (what was run, what it caught)

Every money/PII-touching step went through an adversarial subagent before commit:

- **plan-critic (pre-A):** 15 findings; folded the blockers into the model/service — **plan-row
  locking** (double-deposit), **approved-only headcount vs the package band**, confirm guards,
  **separate marketing-consent table**, derived event date, nickname sanitation, once-only markers,
  ≥2-options+≥1-package to open.
- **security-scanner (A public surface):** validated anonymity / cross-plan authz / double-book /
  INV-1·2·3·12·13; fixed **socket-IP not spoofable XFF**, **per-token vote/edit rate caps**,
  **blocked-invitee write gate**, HTML-tag strip.
- **purge + notification review (D):** 1 blocker + 3 should-fix, all fixed — **B1** slot-less
  drafts never purged → event date floors on `created_at`; **S1** guest emails lingered in
  `NotificationLog` → scrubbed at purge; **S2** low-RSVP counted pre-approved email invites → counts
  actual responders; **S3** open-link RSVP could email arbitrary addresses (bombing) → confirmation
  gated to approved invites.

---

## 6. Parties polish shipped this session (supporting work)

On the same branch (see §8 note): provider + parent **party frontend**, **birthday-parties browse**
(`/parties`) + demo seed, **package CRUD** (edit + unarchive; create/archive pre-existed), the
**empty-date-dropdown** feedback fix, and the **bulk party-date generator** (client expands a date
range × weekdays × time windows into one batch; `add_slots` now dedupes by start-time and the batch
cap is 500).

---

## 7. How to run / try it (dev)

The `party_planner` flag is enabled locally (and in `make seed`).
1. `make db` · `make dev` · `make web-dev` (+ `make seed` for demo party packages with slots).
2. Log in → **Parties → "Start a vote"** (or account menu → **Party plans**) → build a plan from a
   package **that has dates** (seeded demo packages do; or add dates via **For providers → your org →
   Party packages → Add slots** — now a range generator) → set a theme + deadline → **Open voting**.
3. Open the share link in another browser → RSVP → (host approves) → **vote** (confetti) + react →
   watch the countdown/tally.
4. Resolution is clock-driven — in dev the scheduler tick resolves once the deadline passes
   (`make worker`); confirm + deposit use the one-click dev-confirm (no Stripe keys needed).

---

## 8. Git / PRs

Branch chain (stacked, pushed, none merged):
`main` ◂ #1 `docs/governance-and-ext-prd` ◂ #3 `feat/always-on-repositioning` ◂ #4
`feat/A-anyday-sessions` ◂ #5 `feat/B-parties-decisions` ◂ **#6 `feat/parties-frontend`** ◂
**#7 `docs/party-planner-adr`** ◂ **#8 `feat/party-planner`** (holds Milestones A–D + the package
CRUD, dropdown fix, and slot generator). Merge order: #1→#3→#4→#5→#6→#7→#8 (+ #2 standalone seed fix).

> **Note:** the package-CRUD, dropdown-fix, and slot-generator commits are *parties* concerns but
> landed on `feat/party-planner` (PR #8) for push convenience, not on the parties PR #6. Everything
> reaches `main` in the merge order regardless; if cleaner review is wanted they can be merge-forwarded
> onto #6 (no force-push needed).

---

## 9. Known gaps / next steps

- **Real email gateway** — the hard go-live dependency. Emails run through the stub/FakeEmailGateway
  today; the flag stays OFF in prod until real delivery is wired.
- **Live deposit path** (Payment Element in the manage page) needs Stripe **test keys** to verify end
  to end (dev one-click confirm is verified; the whole API contract is verified).
- **Post-tie final-pick notice:** after a tie the invitees aren't told the host's final choice (a
  change-of-plans is only sent when overriding a *real* winner) — small product follow-up.
- **e2e resolution leg:** the Playwright spec drives the invitee loop; resolution→confirm is
  clock-driven and isn't automatable without an admin/clock hook (covered by the 32 backend tests).
- **Timezone:** provider slot times + planner deadlines are entered in the browser's local time
  (correct for the Perth beachhead; make venue TZ explicit before expanding regions).
- **CLAUDE.md Status line** still predates the planner — worth refreshing on merge (the gate matrix
  G2 wording was already updated in `docs/party-planner-adr`).
- Shared dev/test DB had two leaked committed `party_plan` drafts (cleaned); purge tests now assert on
  the specific plan, not a global count — watch for fixture-commit leakage if it recurs.

---

## 10. Where to look

- ADR: `docs/ADR/0011-party-planner-vote-to-book.md` (LOCKED decisions + resolved edges 1–8).
- Backend: `apps/api/src/juggle/modules/party_planner/` (+ `notifications` planner sends, `scheduler`
  tick wiring, `config` knobs, `parties` package CRUD / slot dedup).
- Frontend: `apps/web/src/pages/PartyPlan{s,Manage,Rsvp}Page.vue`,
  `apps/web/src/pages/provider/ProviderOrgPage.vue` (party section + date generator),
  `apps/web/src/lib/{planTheme,confetti,api,types}.ts`.
- Tests: `apps/api/tests/test_party_planner.py` (32), `test_parties.py` (36);
  `apps/web/e2e/party-planner.spec.ts`.
