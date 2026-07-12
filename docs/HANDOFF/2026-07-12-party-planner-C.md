# Handoff — 2026-07-12 — Party Planner Milestone C (gamified layer)

## Scope
Milestone C of the Party Planner (ADR-0011) — the gamified/"addictive" polish on the B surfaces.
On `feat/party-planner-C` (stacked on `feat/party-planner-B`), **not pushed**.

## What was built

### Backend
- **Theme selection** — `PUT /party-planner/plans/{id}/theme`, validated against a closed set
  (`default / dino / space / unicorn`), editable in draft/open. Stored on `party_plan.theme`.
- **Emoji reactions** — new `plan_reaction` table (migration `d3ce3e6e6e17`, round-trips clean;
  `UNIQUE(invite, option, emoji)` makes a tap idempotent/toggleable). `PUT /invite/{token}/react`
  toggles a reaction — **approved invite + open window + closed emoji allow-list** (`❤️🎉🔥😍👍🤩`)
  + per-IP **and** per-token rate limit. Aggregate, **unattributed** counts (`emoji → n`) are added
  to the public `OptionView`. +3 tests (theme set/reject, reaction toggle+aggregate, bad-emoji 400).

### Frontend
- **Theme skins** (`lib/planTheme.ts`) — pure CSS-variable variants (hero gradient, accent, headline
  emoji), no assets. Host **theme picker** in the draft manager; the invitee page re-skins live to
  the host's choice.
- **Ticking countdown** (1s) to the deadline on the invitee page.
- **Confetti on vote** (`lib/confetti.ts`) — self-contained Web Animations burst at the tap point,
  respects `prefers-reduced-motion`, no dependency (CSP-safe).
- **Animated tally bars** (width transition), **⭐ "Birthday kid's pick"** badge, and the who's-in
  board now shows **avatar + nickname**.
- **One-tap emoji reactions** on option cards — counts from the API, own reactions remembered
  client-side (localStorage; the API never attributes them).
- **Host readiness meter** on the open manager — a % + checklist from **real counts only** (INV-12):
  options added / voting open / first RSVP / first vote.

## Privacy (unchanged posture)
Reactions are unattributed (aggregate counts only); the board shows avatar + parent-chosen nickname
only (no child data); votes remain anonymous (own vote/reactions are client-only memory); the token
page stays `noindex`. The readiness meter is real counts, never fabricated (INV-12).

## Verification
- Backend `make check` **255 passed** (28 planner tests), mypy strict, import-linter **2 contracts
  KEPT**. Reaction migration up/down/up verified.
- Frontend: `vue-tsc` clean, `vite build` OK, `vitest` **23 passed** (added `planTheme` unit test).

## Try it in dev
The `party_planner` flag is on locally. Build a plan → pick a **theme** → open → share link → in
another browser RSVP, then **vote** (confetti) and tap **emoji reactions**; watch the **countdown**,
**animated tally**, and the host **readiness meter** move with real activity.

## Known gaps / next (Milestone D)
- **Lifecycle + notifications:** invite / reveal / override "change of plans" / post-resolution
  detail-request emails (stub gateway now), the **low-RSVP nudge** (T-24h) and **re-vote nudge**
  (markers `low_rsvp_nudge_sent_at` / `revote_nudge_sent_at` already on the model), all idempotent
  on the scheduler tick.
- **PII purge job** (edge 7): `party_planner_purge_days` after the event — must also purge the child
  roster on the resulting `PartyBooking` (needs a `parties` purge hook), keep aggregates, and keep
  the detached `plan_marketing_consent`. The account-less child-data collection path still needs
  specifying (host-enters vs scoped token) before it's built.
- **Real email gateway** remains the hard go-live dependency (flag OFF in prod until then).
- Live deposit path (Payment Element in the manage page) still needs Stripe test keys to verify.
