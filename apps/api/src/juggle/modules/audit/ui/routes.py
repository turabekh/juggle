"""HTTP routes for the audit module: read the audit trail (admin only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentAdmin
from juggle.modules.audit.core import service
from juggle.modules.audit.core.schemas import AuditEventOut

router = APIRouter(prefix="/audit", tags=["audit"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[AuditEventOut])
def list_events(
    admin: CurrentAdmin,
    session: SessionDep,
    action: str | None = None,
    entity_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditEventOut]:
    events = service.list_events(
        session, action=action, entity_type=entity_type, limit=limit, offset=offset
    )
    return [AuditEventOut.model_validate(e) for e in events]
