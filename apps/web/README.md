# Juggle Web (Quasar PWA)

Parent-facing marketplace **and** the admin console, built as a Quasar (Vue 3)
app with SSR for SEO on listing pages and an installable PWA shell (PRD §12).
Admin lives behind admin-role auth as a separate surface within this app
(PRD §10.4).

## Scaffolding (not yet generated)

The Quasar app is scaffolded with the official CLI once we start the frontend
milestone (it is interactive / network-dependent, so it is intentionally not
committed as an empty shell yet):

```bash
npm i -g @quasar/cli
cd apps/web
npm init quasar@latest .    # choose: Vue 3, TypeScript, Vite, SSR + PWA, Pinia, ESLint/Prettier
```

Planned structure once generated:

```
apps/web/
├── quasar.config.ts
├── src/
│   ├── pages/          # discovery, listing detail, checkout, bookings, admin/*
│   ├── layouts/        # public shell, admin shell
│   ├── components/
│   ├── stores/         # Pinia (auth, cart, search filters)
│   └── boot/           # axios client → /api/v1, auth guard
└── src-pwa/            # service worker, manifest
```

The API base URL for local dev is `http://localhost:8000/api/v1`; set the API's
`JUGGLE_CORS_ORIGINS` to include the Quasar dev server (`http://localhost:9000`).
