"""HTTP routes for the roster module: provider attendee lists (JSON + CSV)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.roster.core import service
from juggle.modules.roster.core.schemas import AttendanceIn, AttendanceOut, RosterOut

router = APIRouter(prefix="/roster", tags=["roster"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/sessions/{session_id}", response_model=RosterOut)
def get_roster(
    session_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> RosterOut:
    try:
        return service.get_roster(session, session_id=session_id, actor_id=principal.user_id)
    except service.SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc


@router.put(
    "/sessions/{session_id}/attendance/{booking_child_id}", response_model=AttendanceOut
)
def mark_attendance(
    session_id: uuid.UUID,
    booking_child_id: uuid.UUID,
    payload: AttendanceIn,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> AttendanceOut:
    try:
        return service.mark_attendance(
            session,
            session_id=session_id,
            booking_child_id=booking_child_id,
            actor_id=principal.user_id,
            attended=payload.attended,
        )
    except service.SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    except service.NotOnRoster as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That child is not on this session's roster"
        ) from exc


@router.get("/sessions/{session_id}/export.csv")
def export_roster_csv(
    session_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> Response:
    try:
        body = service.roster_csv(session, session_id=session_id, actor_id=principal.user_id)
    except service.SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="roster-{session_id}.csv"'},
    )
