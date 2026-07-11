"""HTTP routes for the catalog module: provider-managed venues, programs, and
sessions, plus a public session-detail view."""

import uuid
from typing import Annotated
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.catalog.core import schemas, service
from juggle.modules.catalog.core.models import ProgramStatus
from juggle.settings import get_settings

router = APIRouter(prefix="/catalog", tags=["catalog"])

SessionDep = Annotated[Session, Depends(get_session)]


def _forbid_non_member(exc: service.NotOrgMember) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organisation")


@router.get("/venues", response_model=list[schemas.VenueOut])
def list_venues(
    organisation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.VenueOut]:
    try:
        venues = service.list_org_venues(
            session, organisation_id=organisation_id, actor_id=principal.user_id
        )
    except service.NotOrgMember as exc:
        raise _forbid_non_member(exc) from exc
    return [schemas.VenueOut.model_validate(v) for v in venues]


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


@router.get("/programs", response_model=list[schemas.ProgramOut])
def list_programs(
    organisation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.ProgramOut]:
    try:
        programs = service.list_org_programs(
            session, organisation_id=organisation_id, actor_id=principal.user_id
        )
    except service.NotOrgMember as exc:
        raise _forbid_non_member(exc) from exc
    return [schemas.ProgramOut.model_validate(p) for p in programs]


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


@router.get("/programs/{program_id}", response_model=schemas.ProgramOut)
def get_program(
    program_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.ProgramOut:
    try:
        program = service.get_owned_program(
            session, program_id=program_id, actor_id=principal.user_id
        )
    except service.ProgramNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Program not found") from exc
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


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap(session: SessionDep) -> Response:
    """XML sitemap of every indexable listing (PRD §7.1 — SEO discovery). A web
    server maps the site root ``/sitemap.xml`` to this endpoint."""
    base = get_settings().public_base_url.rstrip("/")
    urls = [
        "<url>"
        f"<loc>{escape(base)}/sessions/{session_id}</loc>"
        f"<lastmod>{updated_at:%Y-%m-%d}</lastmod>"
        "</url>"
        for session_id, updated_at in service.published_session_refs(session)
    ]
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{''.join(urls)}"
        "</urlset>"
    )
    return Response(content=body, media_type="application/xml")
