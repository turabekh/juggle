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
KEY_SEAT_HOLD_TTL_SECONDS = "seat_hold_ttl_seconds"
KEY_CHECKOUT_WINDOW_SECONDS = "checkout_window_seconds"
KEY_RELIABILITY_CANCELLATION_PENALTY = "reliability_cancellation_penalty"
KEY_SEARCH_DEFAULT_RADIUS_KM = "search_default_radius_km"
KEY_PAYOUT_DELAY_DAYS = "payout_delay_days"
KEY_IMPERSONATION_TTL_MINUTES = "impersonation_ttl_minutes"


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
