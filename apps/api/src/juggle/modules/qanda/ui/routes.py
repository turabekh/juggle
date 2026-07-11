"""HTTP routes for the qanda module (PRD §7.2): listing Q&A."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.qanda.core import service
from juggle.modules.qanda.core.schemas import AnswerIn, QuestionIn, QuestionOut

router = APIRouter(prefix="/qanda", tags=["qanda"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/programs/{program_id}/questions", response_model=list[QuestionOut])
def list_questions(program_id: uuid.UUID, session: SessionDep) -> list[QuestionOut]:
    return service.list_for_program(session, program_id)


@router.post(
    "/programs/{program_id}/questions",
    status_code=status.HTTP_201_CREATED,
    response_model=QuestionOut,
)
def ask_question(
    program_id: uuid.UUID,
    payload: QuestionIn,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> QuestionOut:
    try:
        return service.ask(
            session, program_id=program_id, asker_id=principal.user_id, body=payload.body
        )
    except service.ProgramNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found") from exc


@router.post("/questions/{question_id}/answer", response_model=QuestionOut)
def answer_question(
    question_id: uuid.UUID,
    payload: AnswerIn,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> QuestionOut:
    try:
        return service.answer(
            session,
            question_id=question_id,
            actor_id=principal.user_id,
            answer_text=payload.answer,
        )
    except service.QuestionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found") from exc
    except service.NotProviderMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the provider can answer"
        ) from exc


@router.get("/provider/{organisation_id}/questions", response_model=list[QuestionOut])
def provider_questions(
    organisation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[QuestionOut]:
    try:
        return service.list_for_provider(
            session, organisation_id=organisation_id, actor_id=principal.user_id
        )
    except service.NotProviderMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
