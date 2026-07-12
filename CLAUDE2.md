# CLAUDE2.md — superseded

This file is **no longer authoritative.** Its load-bearing content has been reconciled into
[`CLAUDE.md`](./CLAUDE.md), which is the single source of instructions for Claude Code in this repo:

- the **domain invariants** (INV-1…13) → `CLAUDE.md` §"Domain invariants";
- the **ADR / handoff / adversarial-review process** → `CLAUDE.md` §"Process";
- **git discipline** (never push without asking, feature-ID commits) → `CLAUDE.md` §"Git discipline".

Content from the old draft that did **not** match the actual codebase was intentionally dropped:
the "no docstrings/comments" rule (the code uses docstrings throughout), the divergent module
names (`search_geo`/`growth`/`shared` — the real modules are listed in `CLAUDE.md`), and the
`:5439` host DB port (the app uses the port in `settings.py`). The subagent matrix and PRD-phase-
gate tables were project-specific to that draft and are not carried over; consult `docs/juggle-prd.md`
for scope/phasing.

Do not add a second instructions file — edit `CLAUDE.md`.
