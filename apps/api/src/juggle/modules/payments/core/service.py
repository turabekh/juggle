"""Business logic for the payments module.

All mutations funnel through a module service (no side-door SQL) so the admin
panel and product share one code path (PRD §10.4).
"""
