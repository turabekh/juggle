"""HTTP routes for the comms module (PRD §8.5): provider broadcasts."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.comms.core import service
from juggle.modules.comms.core.schemas import BroadcastIn, BroadcastOut
from juggle.modules.notifications.core.gateway import EmailGateway, get_email_gateway

router = APIRouter(prefix="/comms", tags=["comms"])

SessionDep = Annotated[Session, Depends(get_session)]
EmailGatewayDep = Annotated[EmailGateway, Depends(get_email_gateway)]


@router.post(
    "/sessions/{session_id}/broadcast",
    response_model=BroadcastOut,
    status_code=status.HTTP_201_CREATED,
)
def send_broadcast(
    session_id: uuid.UUID,
    payload: BroadcastIn,
    principal: CurrentPrincipal,
    session: SessionDep,
    email_gateway: EmailGatewayDep,
) -> BroadcastOut:
    try:
        return service.send_broadcast(
            session,
            session_id=session_id,
            actor_id=principal.user_id,
            subject=payload.subject,
            body=payload.body,
            template_key=payload.template_key,
            gateway=email_gateway,
        )
    except service.SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    except service.NoRecipients as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "No confirmed families to message yet"
        ) from exc


@router.get("/sessions/{session_id}/broadcasts", response_model=list[BroadcastOut])
def list_broadcasts(
    session_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[BroadcastOut]:
    try:
        return service.list_broadcasts(
            session, session_id=session_id, actor_id=principal.user_id
        )
    except service.SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
