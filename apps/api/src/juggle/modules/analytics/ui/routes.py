"""HTTP routes for the analytics module (PRD §8.6): provider insights."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.analytics.core import service
from juggle.modules.analytics.core.schemas import OrgAnalytics

router = APIRouter(prefix="/analytics", tags=["analytics"])

SessionDep = Annotated[Session, Depends(get_session)]


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
