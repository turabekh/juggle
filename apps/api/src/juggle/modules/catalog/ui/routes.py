"""HTTP routes for the catalog module: provider-managed venues, programs, and
sessions, plus a public session-detail view."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.catalog.core import schemas, service
from juggle.modules.catalog.core.models import ProgramStatus

router = APIRouter(prefix="/catalog", tags=["catalog"])

SessionDep = Annotated[Session, Depends(get_session)]


def _forbid_non_member(exc: service.NotOrgMember) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organisation")


@router.post("/venues", status_code=status.HTTP_201_CREATED, response_model=schemas.VenueOut)
def create_venue(
    payload: schemas.VenueCreate, principal: CurrentPrincipal, session: SessionDep
) -> schemas.VenueOut:
    try:
        venue = service.create_venue(
            session,
            organisation_id=payload.organisation_id,
            actor_id=principal.user_id,
            name=payload.name,
            address=payload.address,
            suburb=payload.suburb,
            postcode=payload.postcode,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
    except service.NotOrgMember as exc:
        raise _forbid_non_member(exc) from exc
    return schemas.VenueOut.model_validate(venue)


@router.post("/programs", status_code=status.HTTP_201_CREATED, response_model=schemas.ProgramOut)
def create_program(
    payload: schemas.ProgramCreate, principal: CurrentPrincipal, session: SessionDep
) -> schemas.ProgramOut:
    try:
        program = service.create_program(
            session,
            organisation_id=payload.organisation_id,
            actor_id=principal.user_id,
            title=payload.title,
            category=payload.category,
            description=payload.description,
        )
    except service.NotOrgMember as exc:
        raise _forbid_non_member(exc) from exc
    return schemas.ProgramOut.model_validate(program)


@router.post("/programs/{program_id}/publish", response_model=schemas.ProgramOut)
def publish_program(
    program_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.ProgramOut:
    try:
        program = service.set_program_status(
            session,
            program_id=program_id,
            actor_id=principal.user_id,
            status=ProgramStatus.published,
        )
    except service.ProgramNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Program not found") from exc
    except service.OrgSuspended as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Suspended organisations cannot publish"
        ) from exc
    except service.NotOrgMember as exc:
        raise _forbid_non_member(exc) from exc
    return schemas.ProgramOut.model_validate(program)


@router.post(
    "/programs/{program_id}/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.SessionOut,
)
def create_session(
    program_id: uuid.UUID,
    payload: schemas.SessionCreate,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> schemas.SessionOut:
    try:
        created = service.create_session(
            session, program_id=program_id, actor_id=principal.user_id, data=payload
        )
    except service.ProgramNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Program not found") from exc
    except service.VenueNotFound as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Venue not found in this organisation"
        ) from exc
    except service.NotOrgMember as exc:
        raise _forbid_non_member(exc) from exc
    return schemas.SessionOut.model_validate(created)


@router.get("/programs/{program_id}/sessions", response_model=list[schemas.SessionOut])
def list_program_sessions(
    program_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.SessionOut]:
    program = service.get_program(session, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Program not found")
    sessions = service.list_program_sessions(session, program_id)
    return [schemas.SessionOut.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=schemas.SessionDetailOut)
def get_session_detail(
    session_id: uuid.UUID, session: SessionDep
) -> schemas.SessionDetailOut:
    """Public listing detail — only for sessions in a published program."""
    found = service.get_public_session_detail(session, session_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return found
