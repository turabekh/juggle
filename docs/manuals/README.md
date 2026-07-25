# Juggle manuals

Comprehensive, end-to-end manuals for the people who use Juggle.

| Manual | Audience |
| --- | --- |
| [`user-manual.md`](user-manual.md) | Parents and guardians — finding, booking, parties, privacy |
| [`provider-manual.md`](provider-manual.md) | Providers — listing, capacity, rosters, parties, getting paid |
| [`admin-manual.md`](admin-manual.md) | The platform operator — approvals, money, config, support |

## How these relate to `docs/GUIDE-*.md`

The older `docs/GUIDE-user.md`, `docs/GUIDE-admin.md` and `docs/GUIDE-provider.md` are
**short orientation guides**. These manuals are the long-form reference: every screen, every
setting with its real bounds, and a runbook for the admin.

Where they overlap, **the manuals are the fuller and more current source** — they were
written against the code (config registry, route table, audit actions, notification kinds)
rather than from memory.

All three audiences now have a manual. `../GUIDE-provider.md` remains the short version.

## Keeping them true

Two sections go stale fastest, because they mirror code:

- **Admin §9 (Runtime configuration)** — the table of settings, defaults and bounds mirrors
  the `REGISTRY` in `apps/api/src/juggle/modules/config/core/service.py`. Adding a setting
  there means adding a row here.
- **Admin §10 (Feature flags)** — the flags in use.
- **Provider §8 (How the money works)** — the worked example uses the *default* commission
  and GST rates; both are runtime settings an admin can change.

Anything marked *(if enabled)* in the user manual is behind a feature flag and may not be
visible in a given deployment.
