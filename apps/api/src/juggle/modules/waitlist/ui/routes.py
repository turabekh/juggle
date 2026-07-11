"""HTTP routes for the waitlist module (PRD §7.7).

Guardian: join a sold-out session, view own queue/offers, leave.
Provider: queue depth for a session they run.
Admin: ops reconciliation sweep (offer freed seats / expire lapsed offers).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentAdmin, CurrentPrincipal
from juggle.modules.waitlist.core import service
from juggle.modules.waitlist.core.schemas import (
    JoinWaitlistIn,
    SessionWaitlistOut,
    WaitlistEntryOut,
    WaitlistRunResult,
)

router = APIRouter(prefix="/waitlist", tags=["waitlist"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=WaitlistEntryOut, status_code=status.HTTP_201_CREATED)
def join_waitlist(
    payload: JoinWaitlistIn, principal: CurrentPrincipal, session: SessionDep
) -> WaitlistEntryOut:
    try:
        return service.join_waitlist(
            session, session_id=payload.session_id, guardian_id=principal.user_id
        )
    except service.SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc
    except service.SessionNotSoldOut as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This session still has seats — you can book it now"
        ) from exc
    except service.AlreadyOnWaitlist as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You're already on this session's waitlist"
        ) from exc


@router.get("/mine", response_model=list[WaitlistEntryOut])
def my_waitlist(principal: CurrentPrincipal, session: SessionDep) -> list[WaitlistEntryOut]:
    return service.list_for_guardian(session, principal.user_id)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def leave_waitlist(
    entry_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> None:
    try:
        service.leave_waitlist(session, entry_id=entry_id, guardian_id=principal.user_id)
    except service.EntryNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Waitlist entry not found") from exc


@router.get("/sessions/{session_id}", response_model=SessionWaitlistOut)
def session_waitlist(
    session_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> SessionWaitlistOut:
    try:
        return service.session_waitlist(
            session, session_id=session_id, actor_id=principal.user_id
        )
    except service.SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc


@router.post("/process", response_model=WaitlistRunResult)
def process_waitlists(admin: CurrentAdmin, session: SessionDep) -> WaitlistRunResult:
    return service.process_all(session)
