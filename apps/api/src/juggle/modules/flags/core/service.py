"""Flags service: feature flags with on/off, percentage rollout, and targeting
(PRD §10.1). Evaluation is deterministic so a user's bucket is stable.
"""

import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.audit.core import service as audit_service
from juggle.modules.flags.core.models import FeatureFlag


def get_flag(db: Session, key: str) -> FeatureFlag | None:
    return db.scalar(select(FeatureFlag).where(FeatureFlag.key == key))


def list_flags(db: Session) -> list[FeatureFlag]:
    return list(db.scalars(select(FeatureFlag).order_by(FeatureFlag.key)))


def upsert_flag(
    db: Session,
    *,
    key: str,
    enabled: bool,
    rollout_percentage: int = 0,
    targeting: dict[str, Any] | None = None,
    description: str | None = None,
    changed_by_id: uuid.UUID | None = None,
) -> FeatureFlag:
    flag = get_flag(db, key)
    if flag is None:
        flag = FeatureFlag(key=key)
        db.add(flag)
    flag.enabled = enabled
    flag.rollout_percentage = rollout_percentage
    flag.targeting = targeting
    flag.description = description
    db.flush()
    audit_service.record(
        db,
        action="flag.upsert",
        actor_id=changed_by_id,
        entity_type="feature_flag",
        entity_id=key,
        detail={"enabled": enabled, "rollout_percentage": rollout_percentage},
    )
    return flag


def _bucket(key: str, user_id: uuid.UUID) -> int:
    digest = hashlib.sha256(f"{key}:{user_id}".encode()).hexdigest()
    return int(digest, 16) % 100


def is_enabled(
    db: Session,
    key: str,
    *,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
) -> bool:
    flag = get_flag(db, key)
    if flag is None or not flag.enabled:
        return False

    targeting = flag.targeting or {}
    if user_id is not None and str(user_id) in targeting.get("user_ids", []):
        return True
    if org_id is not None and str(org_id) in targeting.get("org_ids", []):
        return True

    if flag.rollout_percentage >= 100:
        return True
    if flag.rollout_percentage <= 0 or user_id is None:
        return False
    return _bucket(key, user_id) < flag.rollout_percentage
