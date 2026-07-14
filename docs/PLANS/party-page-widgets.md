# Plan — Party Page (host-customizable public birthday page + merged voting)

Extends ADR-0011's public invitee surface. The tokenized public page (`/parties/plan/:token`)
becomes a **themed, host-customizable party page** — a hero + a stack of widgets, with the existing
**vote panel as one widget**. The host customizes it from the manage page with a **live preview**,
and can **view/monitor** the guest page + tally.

## Non-negotiable constraint (INV-3 / INV-13 / ADR-0011 §10)

The shared link is **pseudonymous and audience-scoped**: opaque 256-bit token, `noindex`,
deadline-expiring. It carries **no child name, no child photo, no roster** — only theme, a
**parent-chosen** party title/nickname, avatars, and aggregate counts. This mirrors the existing
who's-in board ("pseudonymous by construction"). Host-authored free text (title, welcome message) is
**untrusted**: HTML-stripped, URL-stripped, profanity-masked, length-capped — same pipeline as
custom-option text (edge 8). UI copy steers hosts to nicknames, not surnames. (Residual: a host could
still type a child's name; mitigated by guidance + sanitation + noindex token, consistent with how
the nickname field already works — called out for the security review.)

## Data model (party_plan new columns; one migration)

- `page_title: str | None` — party title / page name (sanitized, config-capped).
- `page_message: str | None` — host welcome note (sanitized, config-capped).
- `hero_avatar: str | None` — big hero avatar key (∈ `AVATAR_KEYS`).
- `page_widgets: JSON (list[str])` — enabled widget keys; `null`/empty ⇒ all on.
- **Reuse `theme`** as the template selector (expand the `THEMES` set — no new column).

## Templates (theme skins — expand `THEMES` / `planTheme.ts`)

~8 preset templates, gendered-leaning + neutral (a **style choice**; the child's gender is never
stored): `default` (party), `unicorn`, `princess`, `superhero`, `dino`, `space`, `rainbow`,
`mermaid`, `jungle`. Each = gradient + accent + hero emoji + decoration emojis.

## Widgets (host-toggleable; vote panel always on)

`welcome` (note + party details), `countdown` (animated + decorations), `board` (pseudonymous
avatars + reactions), `reveal_venue` (winning time/venue/map on resolve).

## Config knobs (INV-11 — bounded, versioned, audited)

- `party_planner_page_title_maxlen` (default 60, 10..120)
- `party_planner_page_message_maxlen` (default 280, 0..1000)

## API

- `PUT /party-planner/plans/{id}/page` — host-only; allowed while `draft`/`open`; body =
  `{title?, message?, hero_avatar?, template?, widgets?}` (partial). Validates + sanitizes.
- Page fields added to `PlanView` (host, for edit+preview) and `PublicPlanView` (invitee, to render).

## Frontend

- `planTheme.ts`: expand to the template set (colours, hero emoji, decorations).
- `PartyHero.vue`: shared hero (template bg + hero avatar + title) — used by public page + preview.
- Public page (`PartyPlanRsvpPage`): render hero + enabled widgets; vote stays interactive.
- Manage page (`PartyPlanManagePage`): a **Party page** editor (template picker, title, hero avatar,
  welcome message, 4 widget toggles) with a **live preview** (`PartyPagePreview.vue`, fed by form
  state + the plan's real options) and a **"View guest page"** link when open.

## Milestones (commit at each green step)

- **A backend**: model + migration + config + service (`update_page`, expanded `THEMES`, widget keys)
  + schemas + route + tests.
- **B templates**: `planTheme.ts` template set (+ backend `THEMES` parity).
- **C public render**: `PartyHero` + widget-driven public page.
- **D host editor + preview**: manage-page customization + live preview + view-guest-page.
- **E**: e2e + security review (public surface) + handoff.

## Invariants touched

INV-3/INV-13 (pseudonymous public surface, untrusted host text), INV-11 (bounded config), INV-12
(counts are real). No money/inventory (INV-1/INV-2 untouched — still a planning layer).
