# Handoff — 2026-07-14 — Party page + one-step voting + discoverability + deployment prep

Session on branch **`feat/party-planner`** (continues the Party Planner / ADR-0011 line; read
`CLAUDE.md`, then the prior handoff `2026-07-12-party-planner-COMPLETE.md`, then this file).

---

## 1. TL;DR

Four pieces of work landed this session:

1. **One-step RSVP-and-vote** — removed the host-approval gate. Anyone with the share link enters
   name + email and votes in one tap; no "waiting to be approved" step. Moderation (block/remove)
   preserved; auto-approval closes the old email-bomb vector by suppressing the RSVP confirmation.
2. **Host-customizable party page** — the tokenized public page became a themed party page: 9
   templates, a big avatar, a party title, a welcome note, and 4 toggleable widgets, with a
   **live phone-framed preview** in the host editor. Voting is merged in as an always-on widget.
   Pseudonymous throughout (INV-3/INV-13); adversarial security review returned **SAFE TO MERGE**.
3. **Discoverability** — a "Your party votes" section on the parties page, plans named by their
   party title everywhere, and a top-level **Party votes** nav link.
4. **Deployment prep** — a production Docker Compose + Caddy edge + a GCP Compute Engine guide,
   **smoke-tested end-to-end** (found and fixed two real bugs).

**State:** backend `make test` **271 passed**, ruff + mypy strict + import-linter (2 contracts) clean;
web `vue-tsc` + build + **Vitest 23** + **Playwright e2e** green. Migration `f8f6357585d2` applied.
`party_planner` flag still **OFF in prod** (email dependency). 6 commits pushed; the deploy commit is
local (see §8).

---

## 2. What shipped (product)

### One-step voting
- Open the share link → enter name + email (+ optional kid count / nickname / avatar) → **tap a
  party** → that single tap creates the RSVP *and* records the vote. No approval, no second step.
- A blocked/removed guest tapping a vote now gets a clear message instead of a silent no-op.

### Party page (host-customizable public page)
- **Host editor** (manage page, draft *and* open): template picker (9), party title, big avatar,
  welcome message, 4 widget toggles, a **live preview**, and a **"View guest page"** link.
- **Public page** (the token link): themed hero (template gradient + host avatar + title +
  decorations) + host-toggled widgets — welcome note, countdown + decorations, who's-coming board +
  reactions, winning venue + map on reveal — with the vote panel always present.
- **Templates** (style choice only; gender never stored): `default, unicorn, princess, superhero,
  dino, space, rainbow, mermaid, jungle`.
- **Widgets** (toggleable; vote always on): `welcome, countdown, board, reveal_venue`.

### Discoverability
- **PartiesPage** shows a "Your party votes" strip (signed-in + has plans): each plan as a card with
  its title, theme glyph, one-line summary, status chip, plus a "New vote" button.
- Plans are named by their **party title** (fallback: first package name) in the strip, the
  `/parties/plans` list, and the manage-page header.
- Top-nav **Party votes** link (signed-in); label aligned across nav, account menu, page heading.

---

## 3. Architecture / changes

### Backend (`party_planner` + `config`)
- **Model** (`party_plan`, migration `f8f6357585d2`): `page_title`, `page_message`, `hero_avatar`
  (nullable), `page_widgets` JSON (empty ⇒ all on; `server_default '[]'` backfills existing rows).
  `approval_required` default flipped **True → False**.
- **Service**: `THEMES` expanded to 9; `WIDGET_KEYS_ORDER`/`WIDGET_KEYS`; `update_page()` full-state
  editor (host-only, draft/open; sanitises untrusted title/message via `_sanitise_public_text`,
  validates template/avatar/widgets against allow-lists); `_page_view()` echoed to host + public
  views; `open_rsvp()` no longer sends a confirmation email (auto-approval bomb-safety) and dropped
  its `email_gateway` param.
- **Config** (INV-11): `party_planner_page_title_maxlen` (60, 10–120),
  `party_planner_page_message_maxlen` (280, 0–1000).
- **API**: `PUT /api/v1/party-planner/plans/{id}/page`. Honeypot receipt now returns
  `status:"approved"` to match a real auto-approved RSVP (removed a tell).
- **Schemas**: `PartyPageView` / `PagePatchIn`; `page` field on `PlanView` + `PublicPlanView`.

### Frontend (`apps/web`)
- `lib/planTheme.ts` — 9 templates (gradient + accent + hero emoji + `decorations[]`).
- `lib/partyPage.ts` — shared `AVATARS`, `WIDGETS`, `widgetOn`, and plan-presentation helpers
  `planDisplayTitle` / `planGlyph` / `planSummary` / `PLAN_STATUS` + `planStatus{Label,Color}`.
- `components/PartyHero.vue` (shared hero), `PartyPagePreview.vue` (phone-framed live preview),
  `PartyPageEditor.vue` (the editor, emits `saved`).
- `pages/PartyPlanRsvpPage.vue` — widget-driven public page + one-tap `voteOrRsvp`.
- `pages/PartyPlanManagePage.vue` — editor in draft + open; header uses the party title.
- `pages/PartiesPage.vue` — "Your party votes" section. `pages/PartyPlansPage.vue` — shared helpers.
- `layouts/MainLayout.vue` — top-nav "Party votes" link.
- `lib/{types,api}.ts` — `PartyPageView`/`PartyPagePatch` + `updatePage()`.

### Deployment (`/`, `apps/web`, `docs`)
- `docker-compose.prod.yml` — internal PostGIS → one-shot `migrate` gate → `api` + `worker` →
  `web` (Caddy on 80/443). Secrets from `.env` only.
- `apps/web/Dockerfile` (multi-stage node build → Caddy), `Caddyfile` (mutually-exclusive `handle`
  blocks: `/api/*` proxied, else SPA history fallback; auto-HTTPS via `SITE_ADDRESS`/`DOMAIN`),
  `.dockerignore`.
- `.env.production.example` (tracked via a `.gitignore` exception) + `docs/DEPLOY.md` (GCP guide).

---

## 4. Invariants (how respected)

- **INV-1/INV-2** untouched — still a planning layer; no holds, no new money code.
- **INV-3/INV-13** — the public page stays pseudonymous behind the opaque `noindex` token: only
  theme, parent-chosen title/nickname, avatars, aggregate counts. Host title/message are **untrusted
  host text** → HTML/URL-stripped, profanity-masked, length-capped (config-bounded) on the write
  path; rendered only via Vue `{{ }}` (no `v-html`). Residual: a host could still *type* a child's
  name — mitigated by UI guidance ("use a nickname, no surnames"), sanitation, and the noindex token
  (same accepted trade-off as the existing nickname field; ADR-0011 §10).
- **INV-11** — the two new page knobs are typed/bounded/versioned/audited; read via `config.service`.
- **INV-12** — every countdown/tally/board number is a real count.

Auto-approval security: RSVP confirmation email suppressed (no spraying arbitrary addresses); the
winner announcement at resolution still emails whoever RSVP'd (bounded by the 20/hr rate limits) —
acceptable while the flag is OFF in prod.

---

## 5. Review gates

- **Adversarial security review** of the party page (independent subagent) — pressure-tested XSS,
  the map-link href, `update_page` authz/lifecycle, public-view leakage, server-side allow-lists,
  migration backfill, config bounds, flag gating. **Verdict: SAFE TO MERGE.** Two nits (below), one
  documented residual (host-typed name).
- **Deployment** was smoke-tested by running the full prod stack: `db → migrate (exit 0) → api
  healthy → worker → Caddy edge`; a signup round-tripped web→api→db; SPA deep-link fallback + `/api`
  proxy verified. Caught + fixed: empty `DOMAIN` collapsing the Caddy config, and `try_files`
  swallowing `/api` before the proxy (→ `handle` blocks).

---

## 6. How to run / try (dev)

`party_planner` flag is enabled locally (via `make seed`).
1. `make db` · `make dev` (API :8000) · `make web-dev` (web :9000). (These were stopped at end of
   session — restart them.)
2. Log in → **Party votes** (top nav) or the "Your party votes" section on **/parties** → open a
   plan → the **Party page** editor with live preview → pick a template, title, avatar, widgets →
   Save → **View guest page**.
3. Open the share link in another browser → enter name + email → tap a party (one-tap RSVP+vote).
4. Resolution is clock-driven — `make worker` once the deadline passes.

Backend tests must run against a clean DB to avoid the shared-DB count fragility; the per-test
fixture now also clears `party_plan` in-transaction (see §9), so `make test` is hermetic on the dev
DB. `make check` before finishing any change.

---

## 7. Deploying (GCP Compute Engine) — see `docs/DEPLOY.md`

Single VM + Docker Compose. Short version: create an `e2-small`+ Ubuntu VM (open 80/443), point a
DNS A record at it, install Docker, clone, `cp .env.production.example .env` and fill in DB password
/ JWT secret / domain, then `docker compose -f docker-compose.prod.yml up -d --build`. Make yourself
admin with the one `psql` command in the guide. Caddy auto-provisions HTTPS once `DOMAIN` resolves.

---

## 8. Git / PRs

Branch `feat/party-planner` (PR #8 in the stack; base `main`; nothing merged). Session commits:

| commit | what | pushed |
| --- | --- | --- |
| `2b0ecbe` | one-step RSVP-and-vote (drop approval gate) | ✅ |
| `0f43027` | feedback instead of silent no-op on blocked vote | ✅ |
| `d436bcc` | party page backend (fields, templates, widgets, config, API) | ✅ |
| `096ba0d` | party page frontend (editor + preview + widget-driven page) | ✅ |
| `439adbe` | "Your party votes" + name plans by title | ✅ |
| `951d488` | top-level "Party votes" nav link | ✅ |
| `f80fda1` | deployment (prod compose + Caddy + GCP guide) | ⛔ **local only** |

`origin/feat/party-planner` is at `951d488`. **Push `f80fda1`** to sync the deploy work.

---

## 9. Known gaps / next steps

- **Real email gateway** — still the hard go-live dependency; `party_planner` stays OFF in prod
  until it lands. Guest emails run through the stub.
- **Stripe** — FakeGateway until `JUGGLE_STRIPE_*` keys are set; live Payment Element needs test keys
  to exercise end to end.
- **Party-page nits** (from the review, non-blocking): (1) the editor's counter limits (60/280) are
  hardcoded client-side rather than read from `/config` — cosmetic, server re-caps; (2) Pydantic's
  outer `max_length` is looser than the config cap, so an absurd title 422s instead of truncating.
- **Post-tie final-pick notice** (carried over) — invitees aren't told the host's final choice after
  a genuine tie.
- **Deploy hardening** — move to Cloud SQL (PostGIS) + Secret Manager + scheduled GCS backups before
  real users (notes in `docs/DEPLOY.md §9`); consider building images in CI → Artifact Registry.
- **Test-infra** — `tests/conftest.py` now clears `party_plan` in the rolled-back per-test tx (like
  config/flags) so the planner's cross-plan count queries are hermetic on the shared dev DB; watch
  for other global-count tests if they appear.
- **Dev DB note** — the user's own committed plans live in the shared dev DB; synthetic `@example.com`
  plans from e2e/screenshot runs were cleaned. Don't delete real (`turaboy@gmail.com`) plans.

---

## 10. Where to look

- Plan/design: `docs/PLANS/party-page-widgets.md`; ADR `docs/ADR/0011-party-planner-vote-to-book.md`.
- Backend: `apps/api/src/juggle/modules/party_planner/` (+ `config` knobs), migration
  `apps/api/alembic/versions/f8f6357585d2_party_page_customization_fields.py`,
  tests `apps/api/tests/test_party_planner.py`.
- Frontend: `apps/web/src/components/Party{Hero,PageEditor,PagePreview}.vue`,
  `apps/web/src/pages/Party{PlanRsvp,PlanManage,Plans,ies}Page.vue`,
  `apps/web/src/lib/{planTheme,partyPage,types,api}.ts`, `apps/web/e2e/party-planner.spec.ts`.
- Deploy: `docker-compose.prod.yml`, `apps/web/{Dockerfile,Caddyfile}`, `.env.production.example`,
  `docs/DEPLOY.md`.
