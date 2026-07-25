# Handoff — 2026-07-25 (afternoon) — Mobile navigation, console at phone width, manuals

Third session of the day, all merged to `main` and deployed. Read `CLAUDE.md`, then the two
earlier handoffs from today (`2026-07-25-status-audit-and-planner-fixtures.md`,
`2026-07-25-milestone-C-request-to-quote.md`), then this.

---

## 1. TL;DR

Everything below is **merged and live in production**. `main` is at `ef4860d` + the seed
script commit; local and origin are in sync.

- **PR #23** — mobile bottom tab bar + provider/admin console drawers.
- **`cb6d287`** — console pages at phone width (pushed straight to `main`, no PR).
- **`51075cc` / `ef4860d`** — `docs/manuals/`: comprehensive user, provider and admin manuals.
- **Seeded accounts** — admin / parent / provider on both local and prod (§5). **One of them
  reset an existing prod password — read that section.**

Two of the three fixes started as "make it look more like an app" and turned out to be
things that were **broken**, not unpolished.

---

## 2. Mobile navigation (PR #23)

**Phones had no primary navigation at all.** The header nav is `gt-xs`, so every destination
hid behind the avatar menu, and a signed-out visitor got the brand and a Sign in button.

A bottom tab bar now carries Discover / Parties / Cart / Sign in signed out, and
Discover / Parties / Bookings / Cart / Account signed in. Cart and Sign in are dropped from
the header on mobile rather than offering the same destination twice; the avatar menu stays
because it holds provider/admin/sign-out that no tab covers.

**Two things that would have shipped silently:**

- **Checkout's Pay button.** `CheckoutPage` and `PartyPackagePage` pin their CTA with
  `position: sticky; bottom: 12px`, which a fixed bar covers — hiding the last step of
  checkout. Both offset by a new `--jg-tabbar-h` custom property (`0` on desktop,
  `58px + env(safe-area-inset-bottom)` on mobile). **If you add another bottom-pinned CTA,
  use that variable.**
- **The site footer** is a sibling of the page container, not inside it, so padding the
  container left the document ending under the bar. The footer carries the padding.

Active state is matched explicitly against route names — `router-link-active` would light
Discover up everywhere, since it's `/`. Visibility is Quasar's CSS breakpoint classes, so it
renders correctly under SSR with no JS.

### Console drawers

Both console layouts hard-coded `<q-drawer :model-value="true">`. Below Quasar's breakpoint
that renders as a modal overlay covering ~63% of a 390px screen, with nothing listening to
`update:model-value` — **so it could not be dismissed, including by the backdrop.** The
provider console was unusable on a phone.

Now `v-model` + `show-if-above`: pinned open on desktop, dismissable overlay on phones, with
a hamburger in the header. Closing happens on nav tap *and* backdrop tap — on tap rather
than only on route change, because tapping the page you're already on is a no-op navigation
that would otherwise leave the overlay stuck.

---

## 3. Console pages at phone width (`cb6d287`)

Audited all 13 console routes at 390px with an overflow detector rather than by eye. Two
pages dragged the whole document sideways (which makes *every* page feel broken):

- **admin/config** (555px) — a flex row trying to fit a description beside a 120px input and
  a Save button. Stacks on mobile.
- **admin/impersonation** (471px) — user search beside a fixed 200px select. Stacks.

Plus **13 dialogs** hardcoding `min-width` 340–520px, clamped to `min(Npx, 92vw)`. Desktop
sizing unchanged; they settle at 359px on a phone. This affected parent-facing dialogs too.

> ### Do not convert the admin tables to Quasar grid mode
>
> It looks like the obvious fix for the wide tables (audit is 1285px) and it **silently
> breaks them**: grid ignores `body-cell-*` slots, and all four tables use them, so
> Approve/Suspend, Hold/Release, End-session and every status chip disappear. I tried it and
> caught it in a screenshot — the approvals rows rendered a bare UUID where the buttons were.
> The tables scroll inside their own container instead, which leaves the page intact.
> `console-mobile-pages.spec.ts` asserts the approvals buttons still render, so a future
> attempt fails loudly instead of silently.

**Still not done:** the tables aren't mobile-*native*. Doing that properly means writing an
`#item` card template per table, which is real work rather than a prop.

---

## 4. Manuals (`51075cc`, `ef4860d`)

`docs/manuals/` — `user-manual.md` (398 lines), `provider-manual.md` (486),
`admin-manual.md` (475), plus a README. The three `GUIDE-*.md` files now point at them as
the short versions.

Written **against the code** — the config table mirrors the `REGISTRY`, the audit list the
recorded actions, the notification table the notification kinds, and route tables were
checked so nothing describes a feature that doesn't exist.

**That fact-check caught five confident falsehoods I had already written.** Worth knowing,
because they're all things a reader would have believed:

| Claim I wrote | Reality |
| --- | --- |
| "A staff member without a verified WWCC cannot be rostered — enforced by the system" | **False and dangerous.** The roster is the list of *children*; there is no staff-assignment feature, so no such gate exists. INV-4 describes a feature that isn't built. Documented as the provider's responsibility instead. |
| Verification badges need WWCC + insurance + ABN together | Four **independent** signals, each satisfied by ≥1 verified record |
| Team members all get the same access | `owner` and `staff` roles — **cancelling a session is owner-only** |
| The four child fields are all Juggle holds | Providers can define **required checkout questions**; answers land on the roster (`BookingChild.form_answers`) |
| Reviews need an *attended* session | A **confirmed booking on a finished session**; attendance isn't the gate |

The money worked example ($50 → $5.00 / $0.50 / $44.50) was verified by calling
`take_rate()`, not by hand.

**Sections that mirror code and will rot:** admin §9 (settings table), admin §10 (flags),
provider §8 (the worked example uses default rates). Noted in the manuals README.

---

## 5. Seeded accounts — read this

`apps/api/scripts/seed_accounts.py` creates an admin, a parent and a provider (with an
approved organisation). Idempotent, passwords supplied via environment variables so nothing
secret is in the repo (INV-9), no children/bookings/payments created, no flags changed.

```
SEED_ADMIN_PASSWORD=… SEED_PARENT_PASSWORD=… SEED_PROVIDER_PASSWORD=… \
    uv run python scripts/seed_accounts.py
```

Run against **local and production**. Accounts: `admin@kidspots.store`,
`parent@kidspots.store`, `provider@kidspots.store` (org "Test Provider Co", approved).
**Local and prod deliberately use different passwords** — a dev credential should never open
production. Credentials were handed over in the session, not written down here.

> **⚠️ `admin@kidspots.store` already existed on production, and the run reset its password.**
> That account pre-dated this session — if someone was using it with a known password, that
> password no longer works and the new one is the one from this session. Nothing was lost
> (the account, its admin flag and its history are intact), but it is a real side effect of
> an idempotent script doing what it says. Verified afterwards: admin gets 200 on the admin
> API, parent and provider correctly get 403, provider owns 1 org, on both environments.

---

## 6. Verification

- 14 mobile Playwright specs (`mobile-tabbar`, `console-mobile-nav`, `console-mobile-pages`)
  — both viewports, both auth states, footer clearance, checkout CTA clearance, drawer
  dismissal three ways, no page overflow on any console route, dialogs that fit.
- `vue-tsc` clean, web build green, 27 Vitest units pass.
- Production checked at 390px after deploy: tab bar pinned to the bottom edge, correct tabs,
  `--jg-tabbar-h` resolving, no page overflow, and the clamp present in the shipped
  `SessionDetailPage` chunk.
- Drive-by: `admin-merge.spec.ts` hardcoded `localhost:8000` and ignored `E2E_API_URL`.

---

## 7. Known gaps / next steps

**The two blockers are credentials, not code:**

1. **Stripe keys.** Prod still reports `{"live":false}` — it runs the `FakeGateway`, so a real
   checkout would confirm a booking and accrue a payout for money never collected. **This is
   the urgent one now that the site is live.**
2. **SMTP credentials.** `party_quotes` and `party_planner` are built, deployed and **dark**
   until email delivery works.

**Also open:**

- **Every e2e run makes billable Claude calls.** `JUGGLE_ANTHROPIC_API_KEY` is in `.env`, so
  the dev API's planner uses the live model — which also makes `planner-add-to-cart.spec.ts`
  flaky (the summary text varies, tripping a strict-mode locator). Same class as the pytest
  leak fixed this morning; the fix here is environmental (run e2e against an API without the
  key), so it wasn't mine to make unilaterally.
- Admin tables not mobile-native (§3); SSR prefetch serialization; deploy hardening
  (Cloud SQL, Secret Manager, scheduled GCS backups — currently container Postgres with
  manual pre-deploy dumps); the deferred per-payout commit for the payout-release crash window.
- **No active gate.** ADR-0006 closed with Milestone C. Everything else in PRD-EXT-1 is
  locked until raised: G1, G3-full, G4, G5, G6, E1/E3, E4, B-series, SMS, SSO, KidSport.

---

## 8. Where to look

- Mobile nav: `apps/web/src/layouts/{MainLayout,ProviderLayout,AdminLayout}.vue`,
  `apps/web/src/css/app.scss` (`--jg-tabbar-h`).
- Console width: `apps/web/src/pages/admin/{AdminConfigPage,AdminImpersonationPage}.vue`,
  and the `min(Npx, 92vw)` dialog clamps across `apps/web/src/pages/`.
- Specs: `apps/web/e2e/{mobile-tabbar,console-mobile-nav,console-mobile-pages}.spec.ts`.
- Manuals: `docs/manuals/`.
- Seeding: `apps/api/scripts/seed_accounts.py`.
- Deploy: `scripts/deploy.sh --backup --iap` (IAP because VM SSH is IP-restricted and home
  IPs move).
