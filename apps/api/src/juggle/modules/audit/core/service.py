"""Audit service: append-only trail of consequential actions (PRD §10.4).

The lowest layer — imports no other module. Everything above records here; rows
are never updated or deleted.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.audit.core.models import AuditEvent


def record(
    db: Session,
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    impersonated_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor_id,
        impersonated_id=impersonated_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail or {},
    )
    db.add(event)
    db.flush()
    return event


def list_events(
    db: Session,
    *,
    action: str | None = None,
    entity_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc())
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    if entity_type is not None:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    stmt = stmt.limit(max(1, min(limit, 500))).offset(max(0, offset))
    return list(db.scalars(stmt))
