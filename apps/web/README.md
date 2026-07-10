# Juggle Web (Quasar PWA)

Parent-facing marketplace for Juggle — a Vite + Vue 3 (TypeScript) + Quasar SPA.

## Run it

```bash
# 1. Backend (from repo root): start Postgres, migrate, seed demo data, run API
make db && make migrate && make seed && make dev      # API on :8000

# 2. Frontend (this app)
make web-install     # or: cd apps/web && npm install
make web-dev         # Quasar dev server on http://localhost:9000
```

The dev server proxies `/api` → `http://localhost:8000`, so no CORS setup is
needed. `make seed` populates an approved provider with published sessions across
Perth suburbs so the marketplace isn't empty.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server (port 9000, `/api` proxied to the backend) |
| `npm run build` | `vue-tsc` typecheck + production build to `dist/` |
| `npm run typecheck` | Type-check only |
| `npm run preview` | Serve the production build |

## Structure

```
src/
├── main.ts               # app bootstrap (Quasar plugins, Pinia, router)
├── App.vue
├── router/               # routes + auth guard
├── layouts/MainLayout.vue# header / nav / footer shell
├── pages/                # Discover, SessionDetail, Cart, Checkout, Bookings,
│                         #   Account, Login, Signup, NotFound
├── components/           # SessionCard, EmptyState
├── stores/               # Pinia: auth, cart (persisted)
├── lib/                  # api (typed client), types, format, sessionMemo
└── css/                  # quasar.variables.scss (brand), app.scss (tokens)
```

**Design system:** brand tokens live in `src/css/quasar.variables.scss` (Quasar
theme) and `src/css/app.scss` (CSS custom properties — colours, spacing, shadows,
radii, the `.jg-card` / `.jg-pill` primitives). Headings use Fraunces, body Inter.

**API layer:** `src/lib/api.ts` is the single typed client. The auth token is held
in a module variable (set by the auth store) and injected via an interceptor, so
there's no store↔client import cycle.

## Flow

Discover (PostGIS search + filters) → Session detail (pick kids → hold seats) →
Cart → Checkout (checkout + confirm) → My bookings. Auth-gated routes redirect to
sign-in and back.

## Admin console

Signed-in admins (`user_account.is_admin`) get an **Admin console** under `/admin`
(also linked from the account menu). `make seed` creates `admin@example.com` /
`supersecret`. Surfaces:

- **Approvals** — approve/suspend providers (a suspended org can't publish).
- **Configuration** — edit the runtime levers (fee %, TTLs, …), bounded & versioned.
- **Feature flags** — create/toggle, rollout %, targeting.
- **Audit log** — every consequential action, filterable, with the true actor.
- **Impersonation** — start a view-as/act-as session; "Enter session" swaps to the
  user's view with a persistent support banner; "Exit" restores the admin.

## Not yet built (follow-ups)

- SSR for SEO on listing pages (PRD §12) — currently SPA.
- PWA service worker / installability, offline shell.
- Provider self-serve console (onboarding, listings, roster) — API partially exists.
- Map view; reviews/waitlists (P1).
