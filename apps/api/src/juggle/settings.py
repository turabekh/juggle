"""Application configuration, loaded from the environment.

Runtime *product* configuration (platform fee %, seat-hold TTL, etc.) lives in
the database and is edited through the admin panel (PRD §10.1). This file holds
only *deployment* configuration — connection strings, secrets, toggles that must
exist before the app can boot.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The `.env` lives at the repo root (next to `.env.example`), but the API is run
# from `apps/api`, so resolve it by absolute path rather than CWD. Missing files
# are ignored (Docker/prod inject real env vars), so this is safe everywhere.
# In dev the tree is <repo>/apps/api/src/juggle/settings.py (parents[4] = repo
# root); in a container the package sits at /app/src/juggle, which is shallower —
# guard the index so a shallow tree resolves to filesystem root (no .env there,
# so it's simply ignored) instead of raising IndexError at import time.
_PARENTS = Path(__file__).resolve().parents
_REPO_ROOT = _PARENTS[4] if len(_PARENTS) > 4 else _PARENTS[-1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JUGGLE_",
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="local")
    debug: bool = Field(default=True)

    # Postgres / PostGIS
    database_url: str = Field(
        default="postgresql+psycopg://juggle:juggle@localhost:5433/juggle",
        description="SQLAlchemy URL. Uses psycopg3 driver + PostGIS-enabled Postgres.",
    )

    # Auth (JWT) — real values injected via env in every non-local environment.
    # Default is ≥32 bytes so local dev doesn't trip pyjwt's weak-key warning.
    jwt_secret: str = Field(default="dev-insecure-secret-change-me-in-prod-0123456789")
    jwt_algorithm: str = Field(default="HS256")
    # Access tokens are short-lived; a DB-backed refresh token (rotated on use,
    # revocable on logout) keeps sessions alive without a long-lived bearer.
    access_token_ttl_minutes: int = Field(default=15)
    refresh_token_ttl_days: int = Field(default=30)

    # SMS one-time-code sign-in (PRD §7.2). When the Twilio creds are unset the
    # app uses an in-memory FakeSmsGateway that logs the code, so dev/CI need no
    # SMS account — mirrors the Stripe/email gateway pattern.
    otp_ttl_minutes: int = Field(default=10)
    otp_max_attempts: int = Field(default=5)
    otp_resend_cooldown_seconds: int = Field(default=60)
    # SMS-bomb / cost controls beyond the per-number resend cooldown: caps on how
    # many codes one number/IP/the whole platform can trigger in a window.
    otp_max_per_number_per_day: int = Field(default=5)
    otp_max_per_ip_per_hour: int = Field(default=5)
    otp_global_max_per_hour: int = Field(default=500)
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_from_number: str = Field(default="")

    # CORS origins for the Quasar PWA during development.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:9000"])

    # Public site origin — used to build absolute URLs in the SEO sitemap (§7.1).
    public_base_url: str = Field(default="http://localhost:9000")

    # Stripe (test mode by default). When stripe_secret_key is unset the app uses
    # the in-memory FakeGateway, so local dev and CI need no Stripe account.
    # Prefixed JUGGLE_ like all app config; the Stripe CLI reads its own STRIPE_API_KEY.
    stripe_secret_key: str = Field(default="")
    stripe_publishable_key: str = Field(default="")
    stripe_webhook_secret: str = Field(default="")

    # AI holiday planner (parent-facing). When anthropic_api_key is unset the planner
    # uses a deterministic RuleBasedPlannerGateway (no LLM, no cost) — same
    # gateway-Protocol fallback pattern as Stripe/email/SMS. Default model per the
    # Anthropic guidance; child PII is never sent to the model (INV-3).
    anthropic_api_key: str = Field(default="")
    anthropic_model: str = Field(default="claude-opus-4-8")

    # Platform legal identity — the supplier on provider commission tax invoices (§8.4,
    # ADR-0002). Real ABN/name injected via env before charging in production.
    platform_legal_name: str = Field(default="Juggle Marketplace Pty Ltd")
    platform_abn: str = Field(default="")


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so settings are parsed once per process."""
    return Settings()
