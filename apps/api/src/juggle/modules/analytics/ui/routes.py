"""HTTP routes for the analytics module (PRD §8.6): provider insights."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentAdmin, CurrentPrincipal
from juggle.modules.analytics.core import service
from juggle.modules.analytics.core.schemas import FunnelOut, OrgAnalytics

router = APIRouter(prefix="/analytics", tags=["analytics"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/funnel", response_model=FunnelOut)
def platform_funnel(
    admin: CurrentAdmin,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> FunnelOut:
    since = datetime.now(UTC) - timedelta(days=days)
    return service.platform_funnel(session, days=days, since=since)


@router.get("/organisations/{organisation_id}", response_model=OrgAnalytics)
def org_analytics(
    organisation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> OrgAnalytics:
    try:
        return service.org_analytics(
            session, organisation_id=organisation_id, actor_id=principal.user_id
        )
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
