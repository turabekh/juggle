"""Config service: versioned, bounded, audit-logged runtime settings (PRD §10.1).

Every operational lever is a registered ``SettingSpec`` with a default and
bounds. The effective value is the current DB row's value, or the default when
unset. Updates insert a new version (the previous ``is_current`` row is
superseded) and are written to the audit trail — no deploy required.

Higher modules read their policy from here through the typed accessors at the
bottom of this file (fee rate, seat-hold TTL, checkout window, ...), replacing
what used to be hardcoded constants.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.audit.core import service as audit_service
from juggle.modules.config.core.models import PlatformSetting

# Setting keys (stable identifiers stored in the DB).
KEY_PLATFORM_FEE_RATE = "platform_fee_rate"
KEY_GST_RATE = "gst_rate"
KEY_SEAT_HOLD_TTL_SECONDS = "seat_hold_ttl_seconds"
KEY_CHECKOUT_WINDOW_SECONDS = "checkout_window_seconds"
KEY_RELIABILITY_CANCELLATION_PENALTY = "reliability_cancellation_penalty"
KEY_SEARCH_DEFAULT_RADIUS_KM = "search_default_radius_km"
KEY_PAYOUT_DELAY_DAYS = "payout_delay_days"
KEY_IMPERSONATION_TTL_MINUTES = "impersonation_ttl_minutes"
KEY_WAITLIST_CLAIM_WINDOW_MINUTES = "waitlist_claim_window_minutes"
KEY_MAX_ACTIVE_HOLDS_PER_GUARDIAN = "max_active_holds_per_guardian"
KEY_PARTY_DEPOSIT_PCT = "party_deposit_pct"
KEY_PARTY_BALANCE_OFFSET_DAYS = "party_balance_offset_days"
KEY_PARTY_BALANCE_CUTOFF_HOURS = "party_balance_cutoff_hours"
KEY_PARTY_BALANCE_RETRY_INTERVAL_HOURS = "party_balance_retry_interval_hours"
KEY_PARTY_BALANCE_MAX_ATTEMPTS = "party_balance_max_attempts"
# Party Planner (ADR-0011)
KEY_PARTY_PLANNER_MAX_OPTIONS = "party_planner_max_options"
KEY_PARTY_PLANNER_MIN_DEADLINE_GAP_HOURS = "party_planner_min_deadline_gap_hours"
KEY_PARTY_PLANNER_LOW_RSVP_THRESHOLD = "party_planner_low_rsvp_threshold"
KEY_PARTY_PLANNER_EXTEND_HOURS = "party_planner_extend_hours"
KEY_PARTY_PLANNER_PURGE_DAYS = "party_planner_purge_days"
KEY_PARTY_PLANNER_RSVP_RATE_PER_HOUR = "party_planner_rsvp_rate_per_hour"
KEY_PARTY_PLANNER_CUSTOM_OPTION_MAXLEN = "party_planner_custom_option_maxlen"
KEY_PARTY_PLANNER_PAGE_TITLE_MAXLEN = "party_planner_page_title_maxlen"
KEY_PARTY_PLANNER_PAGE_MESSAGE_MAXLEN = "party_planner_page_message_maxlen"


@dataclass(frozen=True)
class SettingSpec:
    key: str
    default: float
    kind: type  # int or float
    minimum: float
    maximum: float
    description: str


REGISTRY: dict[str, SettingSpec] = {
    KEY_PLATFORM_FEE_RATE: SettingSpec(
        KEY_PLATFORM_FEE_RATE, 0.10, float, 0.0, 0.20, "Marketplace commission rate (0–20%)"
    ),
    KEY_GST_RATE: SettingSpec(
        KEY_GST_RATE, 0.10, float, 0.0, 0.20, "GST rate on the platform commission (ADR-0002)"
    ),
    KEY_SEAT_HOLD_TTL_SECONDS: SettingSpec(
        KEY_SEAT_HOLD_TTL_SECONDS, 900, int, 60, 3600, "Seat-hold time-to-live (seconds)"
    ),
    KEY_CHECKOUT_WINDOW_SECONDS: SettingSpec(
        KEY_CHECKOUT_WINDOW_SECONDS, 1200, int, 300, 3600, "Payment window after checkout (seconds)"
    ),
    KEY_RELIABILITY_CANCELLATION_PENALTY: SettingSpec(
        KEY_RELIABILITY_CANCELLATION_PENALTY, 0.10, float, 0.0, 1.0,
        "Reliability-score penalty per provider cancellation",
    ),
    KEY_SEARCH_DEFAULT_RADIUS_KM: SettingSpec(
        KEY_SEARCH_DEFAULT_RADIUS_KM, 25.0, float, 1.0, 200.0, "Default search radius (km)"
    ),
    KEY_PAYOUT_DELAY_DAYS: SettingSpec(
        KEY_PAYOUT_DELAY_DAYS, 2, int, 0, 30, "Payout delay after session (days)"
    ),
    KEY_IMPERSONATION_TTL_MINUTES: SettingSpec(
        KEY_IMPERSONATION_TTL_MINUTES, 30, int, 5, 480, "Impersonation session lifetime (minutes)"
    ),
    KEY_WAITLIST_CLAIM_WINDOW_MINUTES: SettingSpec(
        KEY_WAITLIST_CLAIM_WINDOW_MINUTES, 240, int, 15, 2880,
        "Waitlist offer claim window (minutes)",
    ),
    KEY_MAX_ACTIVE_HOLDS_PER_GUARDIAN: SettingSpec(
        KEY_MAX_ACTIVE_HOLDS_PER_GUARDIAN, 8, int, 1, 50,
        "Max concurrent active seat holds per guardian (anti-hoarding)",
    ),
    KEY_PARTY_DEPOSIT_PCT: SettingSpec(
        KEY_PARTY_DEPOSIT_PCT, 30, int, 10, 100,
        "Party booking deposit percentage of the total (ADR-0007)",
    ),
    KEY_PARTY_BALANCE_OFFSET_DAYS: SettingSpec(
        KEY_PARTY_BALANCE_OFFSET_DAYS, 7, int, 0, 30,
        "Days before a party to start charging the balance (ADR-0008)",
    ),
    KEY_PARTY_BALANCE_CUTOFF_HOURS: SettingSpec(
        KEY_PARTY_BALANCE_CUTOFF_HOURS, 72, int, 0, 336,
        "Hours before a party after which an unpaid balance auto-cancels (ADR-0008)",
    ),
    KEY_PARTY_BALANCE_RETRY_INTERVAL_HOURS: SettingSpec(
        KEY_PARTY_BALANCE_RETRY_INTERVAL_HOURS, 48, int, 1, 336,
        "Minimum hours between party balance-charge attempts (ADR-0008)",
    ),
    KEY_PARTY_BALANCE_MAX_ATTEMPTS: SettingSpec(
        KEY_PARTY_BALANCE_MAX_ATTEMPTS, 3, int, 1, 10,
        "Max party balance-charge attempts before auto-cancel (ADR-0008)",
    ),
    KEY_PARTY_PLANNER_MAX_OPTIONS: SettingSpec(
        KEY_PARTY_PLANNER_MAX_OPTIONS, 4, int, 2, 4,
        "Max options a party plan may offer (ADR-0011)",
    ),
    KEY_PARTY_PLANNER_MIN_DEADLINE_GAP_HOURS: SettingSpec(
        KEY_PARTY_PLANNER_MIN_DEADLINE_GAP_HOURS, 24, int, 1, 168,
        "Min hours between a plan deadline and its earliest option slot (ADR-0011)",
    ),
    KEY_PARTY_PLANNER_LOW_RSVP_THRESHOLD: SettingSpec(
        KEY_PARTY_PLANNER_LOW_RSVP_THRESHOLD, 5, int, 0, 100,
        "RSVP count below which a low-participation nudge fires at T-24h (ADR-0011)",
    ),
    KEY_PARTY_PLANNER_EXTEND_HOURS: SettingSpec(
        KEY_PARTY_PLANNER_EXTEND_HOURS, 48, int, 1, 168,
        "One-tap deadline extension length (ADR-0011)",
    ),
    KEY_PARTY_PLANNER_PURGE_DAYS: SettingSpec(
        KEY_PARTY_PLANNER_PURGE_DAYS, 30, int, 1, 365,
        "Days after the event to purge guest PII from a plan (ADR-0011)",
    ),
    KEY_PARTY_PLANNER_RSVP_RATE_PER_HOUR: SettingSpec(
        KEY_PARTY_PLANNER_RSVP_RATE_PER_HOUR, 20, int, 1, 1000,
        "Per-IP/per-token RSVP+vote requests allowed per hour (ADR-0011)",
    ),
    KEY_PARTY_PLANNER_CUSTOM_OPTION_MAXLEN: SettingSpec(
        KEY_PARTY_PLANNER_CUSTOM_OPTION_MAXLEN, 80, int, 10, 200,
        "Max length of a custom option / nickname on a public plan page (ADR-0011)",
    ),
    KEY_PARTY_PLANNER_PAGE_TITLE_MAXLEN: SettingSpec(
        KEY_PARTY_PLANNER_PAGE_TITLE_MAXLEN, 60, int, 10, 120,
        "Max length of the host-set party page title (ADR-0011 party page)",
    ),
    KEY_PARTY_PLANNER_PAGE_MESSAGE_MAXLEN: SettingSpec(
        KEY_PARTY_PLANNER_PAGE_MESSAGE_MAXLEN, 280, int, 0, 1000,
        "Max length of the host-set party page welcome message (ADR-0011 party page)",
    ),
}


class UnknownSetting(Exception):
    """The key is not in the registry."""


class InvalidSettingValue(Exception):
    """The value has the wrong type or is out of bounds."""


def _spec(key: str) -> SettingSpec:
    spec = REGISTRY.get(key)
    if spec is None:
        raise UnknownSetting(key)
    return spec


def _coerce(spec: SettingSpec, raw: Any) -> Any:
    return float(raw) if spec.kind is float else int(raw)


def _validate(spec: SettingSpec, value: Any) -> None:
    if spec.kind is int and not isinstance(value, int):
        raise InvalidSettingValue(f"{spec.key} must be an integer")
    if spec.kind is float and not isinstance(value, int | float):
        raise InvalidSettingValue(f"{spec.key} must be a number")
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        raise InvalidSettingValue(f"{spec.key} must be numeric, not boolean")
    if not (spec.minimum <= value <= spec.maximum):
        raise InvalidSettingValue(
            f"{spec.key} must be between {spec.minimum} and {spec.maximum}"
        )


def _current_row(db: Session, key: str) -> PlatformSetting | None:
    return db.scalar(
        select(PlatformSetting).where(
            PlatformSetting.key == key, PlatformSetting.is_current.is_(True)
        )
    )


def get_value(db: Session, key: str) -> Any:
    spec = _spec(key)
    row = _current_row(db, key)
    if row is None:
        return spec.default
    return _coerce(spec, row.value.get("value"))


def set_value(
    db: Session,
    *,
    key: str,
    value: Any,
    changed_by_id: uuid.UUID | None,
    note: str | None = None,
) -> PlatformSetting:
    spec = _spec(key)
    _validate(spec, value)
    current = _current_row(db, key)
    version = (current.version + 1) if current is not None else 1
    if current is not None:
        current.is_current = False
        db.flush()
    row = PlatformSetting(
        key=key,
        value={"value": value},
        version=version,
        is_current=True,
        changed_by_id=changed_by_id,
        note=note,
    )
    db.add(row)
    db.flush()
    audit_service.record(
        db,
        action="config.set",
        actor_id=changed_by_id,
        entity_type="platform_setting",
        entity_id=key,
        detail={"value": value, "version": version},
    )
    return row


def effective_settings(db: Session) -> dict[str, Any]:
    return {key: get_value(db, key) for key in REGISTRY}


def history(db: Session, key: str) -> list[PlatformSetting]:
    _spec(key)
    return list(
        db.scalars(
            select(PlatformSetting)
            .where(PlatformSetting.key == key)
            .order_by(PlatformSetting.version.desc())
        )
    )


# --- Typed accessors used by higher modules --------------------------------

def platform_fee_rate(db: Session) -> float:
    return float(get_value(db, KEY_PLATFORM_FEE_RATE))


def gst_rate(db: Session) -> float:
    return float(get_value(db, KEY_GST_RATE))


def seat_hold_ttl_seconds(db: Session) -> int:
    return int(get_value(db, KEY_SEAT_HOLD_TTL_SECONDS))


def checkout_window_seconds(db: Session) -> int:
    return int(get_value(db, KEY_CHECKOUT_WINDOW_SECONDS))


def reliability_cancellation_penalty(db: Session) -> float:
    return float(get_value(db, KEY_RELIABILITY_CANCELLATION_PENALTY))


def search_default_radius_km(db: Session) -> float:
    return float(get_value(db, KEY_SEARCH_DEFAULT_RADIUS_KM))


def payout_delay_days(db: Session) -> int:
    return int(get_value(db, KEY_PAYOUT_DELAY_DAYS))


def impersonation_ttl_minutes(db: Session) -> int:
    return int(get_value(db, KEY_IMPERSONATION_TTL_MINUTES))


def waitlist_claim_window_minutes(db: Session) -> int:
    return int(get_value(db, KEY_WAITLIST_CLAIM_WINDOW_MINUTES))


def max_active_holds_per_guardian(db: Session) -> int:
    return int(get_value(db, KEY_MAX_ACTIVE_HOLDS_PER_GUARDIAN))


def party_deposit_pct(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_DEPOSIT_PCT))


def party_balance_offset_days(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_BALANCE_OFFSET_DAYS))


def party_balance_cutoff_hours(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_BALANCE_CUTOFF_HOURS))


def party_balance_retry_interval_hours(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_BALANCE_RETRY_INTERVAL_HOURS))


def party_balance_max_attempts(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_BALANCE_MAX_ATTEMPTS))


def party_planner_max_options(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_PLANNER_MAX_OPTIONS))


def party_planner_min_deadline_gap_hours(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_PLANNER_MIN_DEADLINE_GAP_HOURS))


def party_planner_low_rsvp_threshold(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_PLANNER_LOW_RSVP_THRESHOLD))


def party_planner_extend_hours(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_PLANNER_EXTEND_HOURS))


def party_planner_purge_days(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_PLANNER_PURGE_DAYS))


def party_planner_rsvp_rate_per_hour(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_PLANNER_RSVP_RATE_PER_HOUR))


def party_planner_custom_option_maxlen(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_PLANNER_CUSTOM_OPTION_MAXLEN))


def party_planner_page_title_maxlen(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_PLANNER_PAGE_TITLE_MAXLEN))


def party_planner_page_message_maxlen(db: Session) -> int:
    return int(get_value(db, KEY_PARTY_PLANNER_PAGE_MESSAGE_MAXLEN))
