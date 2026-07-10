# Juggle API

FastAPI backend for the Juggle marketplace. Python 3.12+, SQLAlchemy 2 +
PostGIS, managed with [`uv`](https://docs.astral.sh/uv/).

## Layout

```
apps/api/
├── pyproject.toml          # deps, ruff/mypy/pytest + import-linter contracts
├── alembic.ini, alembic/   # migrations
├── src/juggle/
│   ├── main.py             # app factory + /health
│   ├── api.py              # aggregates every module router under /api/v1
│   ├── settings.py         # deployment config (env, JUGGLE_ prefix)
│   ├── db.py               # engine, session, declarative Base
│   └── modules/<name>/     # one package per PRD §12 module
│       ├── core/           # domain: models, service (NO fastapi imports)
│       └── ui/             # FastAPI router
└── tests/
```

**Module boundaries** are enforced by import-linter (`make contracts`):
`core` may not import FastAPI/`ui`, and modules stay independent of each other's
internals. Cross-module calls will go through explicit service interfaces.

Modules: `identity, org, catalog, inventory, booking, payments, roster,
notifications, search, admin, config, flags, audit`.

## Quickstart

```bash
make install      # uv sync --extra dev
make db           # start Postgres/PostGIS in Docker
make dev          # run API at http://localhost:8000  (docs at /docs)
make check        # lint + typecheck + contracts + tests
```
