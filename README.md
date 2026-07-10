# Juggle 🤹

A two-sided **booking marketplace for kids' school-holiday activities and birthday parties**, launching in Perth, Australia. Parents search by suburb, date, and child age and book across multiple providers in one cart with **live seat availability**; providers get free self-serve tools to list sessions, manage rosters, and get paid; and a first-class admin console runs the whole thing.

> "Juggle" is a working title pending a name/trademark check. See [`docs/juggle-prd.md`](docs/juggle-prd.md) for the full product spec.

**Status:** pre-gate scaffold. The module architecture, tooling, and a booting API skeleton are in place; feature milestones are not built yet.

## Tech stack

- **Backend:** FastAPI (Python 3.12+), managed with [`uv`](https://docs.astral.sh/uv/)
- **Database:** PostgreSQL + **PostGIS**, SQLAlchemy 2 + Alembic
- **Frontend:** Quasar (Vue 3 + TypeScript) — SSR + PWA *(not scaffolded yet — see [`apps/web/README.md`](apps/web/README.md))*
- **Payments:** Stripe Connect Express *(later milestone)*
- **Module boundaries** enforced by [import-linter](https://import-linter.readthedocs.io/) (core/ui split)

## Repository layout

```
apps/
  api/     FastAPI backend — 13 domain modules with a core/ui split
  web/     Quasar PWA (parent marketplace + admin console) — placeholder
docs/
  juggle-prd.md   Full product requirements — the source of truth
docker-compose.yml, Makefile, .env.example
```

## Getting started

Prerequisites: **Python 3.12+**, [`uv`](https://docs.astral.sh/uv/), and **Docker** (for Postgres/PostGIS).

```bash
cp .env.example .env

make install     # install backend deps (uv sync --extra dev)
make db          # start Postgres/PostGIS in Docker
make dev         # run the API at http://localhost:8000  (docs at /docs)
```

Verify everything is wired up:

```bash
make check       # ruff + mypy (strict) + import-linter contracts + pytest
```

Run `make help` for all shortcuts.

## Architecture in one paragraph

The API is organised into the 13 domain modules from the PRD (`identity, org, catalog, inventory, booking, payments, roster, notifications, search, admin, config, flags, audit`). Each module has a **`core/`** domain layer (models + services, no web framework) and a **`ui/`** layer (its FastAPI router). import-linter enforces that `core` never imports the web layer and that modules don't reach into each other's internals. Inventory correctness (no oversell, seat holds with TTL) is guaranteed at the database layer, and product configuration (fees, TTLs, taxonomy, flags) is runtime-editable through the admin console rather than hard-coded. See [`CLAUDE.md`](CLAUDE.md) for the engineering conventions and [`docs/juggle-prd.md`](docs/juggle-prd.md) for the product spec.

## Building this with Claude Code

This repo is set up for [Claude Code](https://claude.com/claude-code): `CLAUDE.md` carries the conventions and guardrails, and `docs/juggle-prd.md` is the full spec with requirement IDs and phasing. Work through the MVP milestones one vertical slice at a time.

## License

TBD — add a `LICENSE` before publishing.
