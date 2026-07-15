"""HTTP route for the AI holiday planner (parent-facing).

Gated on the ``planner`` feature flag (404 when off), like the party planner.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.flags.core import service as flags_service
from juggle.modules.planner.core import schemas, service
from juggle.modules.planner.core.gateway import PlannerGateway, get_planner_gateway

router = APIRouter(prefix="/planner", tags=["planner"])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[PlannerGateway, Depends(get_planner_gateway)]


@router.post("/plan", response_model=schemas.PlanOut)
def build_plan(
    payload: schemas.PlanRequest,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
) -> schemas.PlanOut:
    if not flags_service.is_enabled(session, "planner", user_id=principal.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if payload.date_to < payload.date_from:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "date_to before date_from")
    return service.build_plan(session, request=payload, gateway=gateway)
