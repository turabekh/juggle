"""Q&A service (PRD §7.2): parents ask questions on a listing, the provider
answers, everyone reads. Structured (no chat threads). Sits above ``booking`` in
the layering; reads catalog for the program→org link, org for answer authority,
identity for a privacy-preserving asker byline, and audits both actions.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.audit.core import service as audit_service
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.identity.core.models import UserAccount
from juggle.modules.org.core import service as org_service
from juggle.modules.qanda.core.models import ListingQuestion
from juggle.modules.qanda.core.schemas import QuestionOut


class ProgramNotFound(Exception):
    """No such program to ask about."""


class QuestionNotFound(Exception):
    """No such question."""


class NotProviderMember(Exception):
    """Only a member of the listing's organisation may answer."""


def _asker_label(user: UserAccount | None) -> str:
    if user is not None and user.full_name:
        first = user.full_name.strip().split(" ", 1)[0]
        if first:
            return first
    return "A parent"


def _out(db: Session, q: ListingQuestion) -> QuestionOut:
    asker = db.get(UserAccount, q.asker_id) if q.asker_id is not None else None
    return QuestionOut(
        id=q.id,
        program_id=q.program_id,
        body=q.body,
        answer=q.answer,
        answered_at=q.answered_at,
        asker_label=_asker_label(asker),
        created_at=q.created_at,
    )


def ask(
    db: Session, *, program_id: uuid.UUID, asker_id: uuid.UUID, body: str
) -> QuestionOut:
    program = catalog_service.get_program(db, program_id)
    if program is None:
        raise ProgramNotFound(str(program_id))
    question = ListingQuestion(
        program_id=program_id,
        organisation_id=program.organisation_id,
        asker_id=asker_id,
        body=body.strip(),
    )
    db.add(question)
    db.flush()
    audit_service.record(
        db,
        action="qanda.asked",
        actor_id=asker_id,
        entity_type="listing_question",
        entity_id=str(question.id),
        detail={"program_id": str(program_id)},
    )
    return _out(db, question)


def answer(
    db: Session, *, question_id: uuid.UUID, actor_id: uuid.UUID, answer_text: str
) -> QuestionOut:
    question = db.get(ListingQuestion, question_id)
    if question is None:
        raise QuestionNotFound(str(question_id))
    if org_service.get_member(db, question.organisation_id, actor_id) is None:
        raise NotProviderMember(str(question.organisation_id))
    question.answer = answer_text.strip()
    question.answered_at = datetime.now(UTC)
    question.answered_by_id = actor_id
    db.flush()
    audit_service.record(
        db,
        action="qanda.answered",
        actor_id=actor_id,
        entity_type="listing_question",
        entity_id=str(question.id),
    )
    return _out(db, question)


def list_for_program(db: Session, program_id: uuid.UUID) -> list[QuestionOut]:
    """Public: answered questions first, then newest unanswered."""
    questions = db.scalars(
        select(ListingQuestion)
        .where(ListingQuestion.program_id == program_id)
        .order_by(ListingQuestion.created_at.desc())
    )
    return [_out(db, q) for q in questions]


def list_for_provider(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> list[QuestionOut]:
    """Provider inbox — unanswered first so they know what needs a reply."""
    if org_service.get_member(db, organisation_id, actor_id) is None:
        raise NotProviderMember(str(organisation_id))
    questions = db.scalars(
        select(ListingQuestion)
        .where(ListingQuestion.organisation_id == organisation_id)
        .order_by(
            ListingQuestion.answer.is_not(None),  # unanswered (None) first
            ListingQuestion.created_at.desc(),
        )
    )
    return [_out(db, q) for q in questions]
