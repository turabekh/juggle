"""HTTP routes for the reviews module (PRD §7.6).

Public: read published reviews + rating summary for a provider/listing.
Guardian: submit a review, list own reviews + reviewable bookings.
Provider: list reviews for an org they belong to, add a right-of-reply.
Admin: moderation queue + approve/reject.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentAdmin, CurrentPrincipal
from juggle.modules.reviews.core import service
from juggle.modules.reviews.core.models import ReviewStatus
from juggle.modules.reviews.core.schemas import (
    ModerateIn,
    ProviderReplyIn,
    ReviewableBooking,
    ReviewListOut,
    ReviewOut,
    ReviewSubmitIn,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])

SessionDep = Annotated[Session, Depends(get_session)]


# --- public ------------------------------------------------------------------


@router.get("/organisations/{organisation_id}", response_model=ReviewListOut)
def list_organisation_reviews(
    organisation_id: uuid.UUID, session: SessionDep
) -> ReviewListOut:
    return service.list_for_organisation(session, organisation_id)


@router.get("/programs/{program_id}", response_model=ReviewListOut)
def list_program_reviews(program_id: uuid.UUID, session: SessionDep) -> ReviewListOut:
    return service.list_for_program(session, program_id)


# --- guardian ----------------------------------------------------------------


@router.get("/reviewable", response_model=list[ReviewableBooking])
def reviewable_bookings(
    principal: CurrentPrincipal, session: SessionDep
) -> list[ReviewableBooking]:
    return service.reviewable_bookings(session, principal.user_id)


@router.get("/mine", response_model=list[ReviewOut])
def my_reviews(principal: CurrentPrincipal, session: SessionDep) -> list[ReviewOut]:
    return service.list_for_author(session, principal.user_id)


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def submit_review(
    payload: ReviewSubmitIn, principal: CurrentPrincipal, session: SessionDep
) -> ReviewOut:
    try:
        return service.submit_review(
            session,
            booking_id=payload.booking_id,
            author_id=principal.user_id,
            rating=payload.rating,
            body=payload.body,
        )
    except service.BookingNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found") from exc
    except service.BookingNotReviewable as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You can only review a confirmed booking after the session has finished",
        ) from exc
    except service.AlreadyReviewed as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You have already reviewed this booking"
        ) from exc
    except service.ChildNameInReview as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Please remove your child's name from the review before submitting",
        ) from exc


# --- provider ----------------------------------------------------------------


@router.get("/provider/{organisation_id}", response_model=list[ReviewOut])
def provider_reviews(
    organisation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[ReviewOut]:
    try:
        return service.list_for_provider(
            session, organisation_id=organisation_id, actor_id=principal.user_id
        )
    except service.NotProviderMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc


@router.post("/{review_id}/reply", response_model=ReviewOut)
def reply_to_review(
    review_id: uuid.UUID,
    payload: ProviderReplyIn,
    principal: CurrentPrincipal,
    session: SessionDep,
) -> ReviewOut:
    try:
        return service.provider_reply(
            session, review_id=review_id, actor_id=principal.user_id, reply=payload.reply
        )
    except service.ReviewNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found") from exc
    except service.NotProviderMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    except service.ReviewNotPublished as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only published reviews can be replied to"
        ) from exc


# --- admin -------------------------------------------------------------------


@router.get("/moderation/queue", response_model=list[ReviewOut])
def moderation_queue(
    admin: CurrentAdmin,
    session: SessionDep,
    review_status: ReviewStatus = ReviewStatus.pending,
) -> list[ReviewOut]:
    return service.list_for_moderation(session, status=review_status)


@router.post("/{review_id}/moderate", response_model=ReviewOut)
def moderate_review(
    review_id: uuid.UUID,
    payload: ModerateIn,
    admin: CurrentAdmin,
    session: SessionDep,
) -> ReviewOut:
    try:
        return service.moderate(
            session,
            review_id=review_id,
            moderator_id=admin.user_id,
            approve=payload.approve,
            reason=payload.reason,
        )
    except service.ReviewNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found") from exc
