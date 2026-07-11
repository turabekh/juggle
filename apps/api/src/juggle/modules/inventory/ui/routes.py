"""HTTP routes for the inventory module: seat holds and live availability."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.inventory.core import schemas, service

router = APIRouter(prefix="/inventory", tags=["inventory"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/holds", status_code=status.HTTP_201_CREATED, response_model=schemas.HoldOut)
def create_hold(
    payload: schemas.HoldCreate, principal: CurrentPrincipal, session: SessionDep
) -> schemas.HoldOut:
    try:
        hold, _ = service.hold_seats(
            session,
            session_id=payload.session_id,
            held_by_id=principal.user_id,
            quantity=payload.quantity,
        )
    except service.SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc
    except service.TooManyHolds as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You already have {exc.limit} seats on hold — check out or release some first.",
        ) from exc
    except service.SoldOut as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Sold out — {exc.remaining} seat(s) remaining"
        ) from exc
    return schemas.HoldOut.model_validate(hold)


@router.delete("/holds/{hold_id}", status_code=status.HTTP_204_NO_CONTENT)
def release_hold(
    hold_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> None:
    try:
        service.release_hold(session, hold_id=hold_id, actor_id=principal.user_id)
    except service.HoldNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hold not found") from exc


@router.get("/sessions/{session_id}/availability", response_model=schemas.AvailabilityOut)
def get_availability(session_id: uuid.UUID, session: SessionDep) -> schemas.AvailabilityOut:
    session_obj = service.availability(session, session_id)
    if session_obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return schemas.AvailabilityOut(
        session_id=session_obj.id,
        capacity=session_obj.capacity,
        seats_taken=session_obj.seats_taken,
        seats_remaining=session_obj.seats_remaining,
    )
