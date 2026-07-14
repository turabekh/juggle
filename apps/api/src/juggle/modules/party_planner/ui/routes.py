"""HTTP routes for the Party Planner (ADR-0011).

Two surfaces: authenticated host management, and a public **tokenized** invitee surface (no
account). The public routes are rate-limited, honeypot-guarded, and return an indistinguishable
generic 404 for any invalid/expired/unknown token (no enumeration oracle). Everything is gated on
the ``party_planner`` feature flag — 404 when off.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.flags.core import service as flags_service
from juggle.modules.notifications.core.gateway import EmailGateway, get_email_gateway
from juggle.modules.parties.core import service as parties_service
from juggle.modules.party_planner.core import schemas, service
from juggle.modules.party_planner.core.models import PlanInviteStatus
from juggle.modules.payments.core.gateway import PaymentGateway, get_payment_gateway

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[PaymentGateway, Depends(get_payment_gateway)]
EmailGatewayDep = Annotated[EmailGateway, Depends(get_email_gateway)]

_GENERIC_404 = HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def _require_flag(session: SessionDep) -> None:
    if not flags_service.is_enabled(session, "party_planner"):
        raise _GENERIC_404


router = APIRouter(
    prefix="/party-planner", tags=["party-planner"], dependencies=[Depends(_require_flag)]
)


def _client_ip(request: Request) -> str:
    # Use the actual socket peer, NOT X-Forwarded-For — the leftmost XFF entry is client-spoofable
    # and would defeat the per-IP cap. A real proxy deployment must set the peer via trusted
    # proxy-header middleware; until that's configured, the socket address is the safe key.
    return request.client.host if request.client else "unknown"


# --- Host: plan lifecycle --------------------------------------------------


def _host_plan(session: Session, plan_id: uuid.UUID, actor_id: uuid.UUID) -> schemas.PlanView:
    plan = service.get_plan(session, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    if plan.host_user_id != actor_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your plan")
    return service.host_plan_view(session, plan)


@router.post("/plans", status_code=status.HTTP_201_CREATED, response_model=schemas.PlanView)
def create_plan(
    body: schemas.CreatePlanIn, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PlanView:
    plan = service.create_plan(session, host_id=principal.user_id, theme=body.theme)
    return service.host_plan_view(session, plan)


@router.get("/plans", response_model=list[schemas.PlanView])
def list_plans(principal: CurrentPrincipal, session: SessionDep) -> list[schemas.PlanView]:
    return [
        service.host_plan_view(session, p)
        for p in service.list_host_plans(session, principal.user_id)
    ]


@router.get("/plans/{plan_id}", response_model=schemas.PlanView)
def get_plan(
    plan_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PlanView:
    return _host_plan(session, plan_id, principal.user_id)


def _map_host_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.PlanNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    if isinstance(exc, service.NotPlanHost):
        return HTTPException(status.HTTP_403_FORBIDDEN, "Not your plan")
    if isinstance(exc, service.OptionNotFound | service.InviteNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if isinstance(
        exc,
        service.PlanNotDraft | service.PlanNotOpen | service.PlanNotResolved
        | service.NotOpenable | service.TooManyOptions | service.DuplicateCustomOption
        | service.DeadlineInvalid | service.OptionNotEligible | service.SlotUnavailable,
    ):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc) or "Invalid request")
    if isinstance(exc, parties_service.HeadcountOutOfBand):
        return HTTPException(status.HTTP_400_BAD_REQUEST, "Headcount outside the package band")
    raise exc


@router.post("/plans/{plan_id}/options/package", response_model=schemas.PlanView)
def add_package_option(
    plan_id: uuid.UUID, body: schemas.AddPackageOptionIn,
    principal: CurrentPrincipal, session: SessionDep,
) -> schemas.PlanView:
    try:
        service.add_package_option(
            session, plan_id=plan_id, actor_id=principal.user_id,
            package_id=body.package_id, slot_id=body.slot_id,
        )
    except Exception as exc:
        raise _map_host_error(exc) from exc
    return _host_plan(session, plan_id, principal.user_id)


@router.post("/plans/{plan_id}/options/custom", response_model=schemas.PlanView)
def add_custom_option(
    plan_id: uuid.UUID, body: schemas.AddCustomOptionIn,
    principal: CurrentPrincipal, session: SessionDep,
) -> schemas.PlanView:
    try:
        service.add_custom_option(
            session, plan_id=plan_id, actor_id=principal.user_id, text=body.text
        )
    except Exception as exc:
        raise _map_host_error(exc) from exc
    return _host_plan(session, plan_id, principal.user_id)


@router.delete("/plans/{plan_id}/options/{option_id}", response_model=schemas.PlanView)
def remove_option(
    plan_id: uuid.UUID, option_id: uuid.UUID,
    principal: CurrentPrincipal, session: SessionDep,
) -> schemas.PlanView:
    try:
        service.remove_option(
            session, plan_id=plan_id, actor_id=principal.user_id, option_id=option_id
        )
    except Exception as exc:
        raise _map_host_error(exc) from exc
    return _host_plan(session, plan_id, principal.user_id)


@router.put("/plans/{plan_id}/ranking", response_model=schemas.PlanView)
def set_ranking(
    plan_id: uuid.UUID, body: schemas.RankingIn,
    principal: CurrentPrincipal, session: SessionDep,
) -> schemas.PlanView:
    try:
        service.set_ranking(
            session, plan_id=plan_id, actor_id=principal.user_id, ordered_option_ids=body.option_ids
        )
    except Exception as exc:
        raise _map_host_error(exc) from exc
    return _host_plan(session, plan_id, principal.user_id)


@router.put("/plans/{plan_id}/deadline", response_model=schemas.PlanView)
def set_deadline(
    plan_id: uuid.UUID, body: schemas.DeadlineIn,
    principal: CurrentPrincipal, session: SessionDep,
) -> schemas.PlanView:
    try:
        service.set_deadline(
            session, plan_id=plan_id, actor_id=principal.user_id, deadline_at=body.deadline_at
        )
    except Exception as exc:
        raise _map_host_error(exc) from exc
    return _host_plan(session, plan_id, principal.user_id)


@router.put("/plans/{plan_id}/theme", response_model=schemas.PlanView)
def set_theme(
    plan_id: uuid.UUID, body: schemas.ThemeIn,
    principal: CurrentPrincipal, session: SessionDep,
) -> schemas.PlanView:
    try:
        service.set_theme(session, plan_id=plan_id, actor_id=principal.user_id, theme=body.theme)
    except service.InvalidTheme as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown theme") from exc
    except Exception as exc:
        raise _map_host_error(exc) from exc
    return _host_plan(session, plan_id, principal.user_id)


@router.post("/plans/{plan_id}/open", response_model=schemas.PlanView)
def open_plan(
    plan_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PlanView:
    try:
        service.open_plan(session, plan_id=plan_id, actor_id=principal.user_id)
    except Exception as exc:
        raise _map_host_error(exc) from exc
    return _host_plan(session, plan_id, principal.user_id)


@router.post("/plans/{plan_id}/extend", response_model=schemas.PlanView)
def extend_deadline(
    plan_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PlanView:
    try:
        service.extend_deadline(session, plan_id=plan_id, actor_id=principal.user_id)
    except Exception as exc:
        raise _map_host_error(exc) from exc
    return _host_plan(session, plan_id, principal.user_id)


@router.post("/plans/{plan_id}/invites", response_model=schemas.PlanView)
def add_invites(
    plan_id: uuid.UUID, body: schemas.EmailInvitesIn,
    principal: CurrentPrincipal, session: SessionDep, email_gateway: EmailGatewayDep,
) -> schemas.PlanView:
    try:
        service.add_email_invites(
            session, plan_id=plan_id, actor_id=principal.user_id,
            recipients=[(i.email, i.name) for i in body.invites], email_gateway=email_gateway,
        )
    except Exception as exc:
        raise _map_host_error(exc) from exc
    return _host_plan(session, plan_id, principal.user_id)


def _set_invite_status(
    session: Session, plan_id: uuid.UUID, invite_id: uuid.UUID, actor_id: uuid.UUID,
    new_status: PlanInviteStatus,
) -> schemas.PlanView:
    try:
        service.set_invite_status(
            session, plan_id=plan_id, actor_id=actor_id, invite_id=invite_id, status=new_status
        )
    except Exception as exc:
        raise _map_host_error(exc) from exc
    return _host_plan(session, plan_id, actor_id)


@router.post("/plans/{plan_id}/invites/{invite_id}/approve", response_model=schemas.PlanView)
def approve_invite(
    plan_id: uuid.UUID, invite_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PlanView:
    return _set_invite_status(
        session, plan_id, invite_id, principal.user_id, PlanInviteStatus.approved
    )


@router.post("/plans/{plan_id}/invites/{invite_id}/remove", response_model=schemas.PlanView)
def remove_invite(
    plan_id: uuid.UUID, invite_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PlanView:
    return _set_invite_status(
        session, plan_id, invite_id, principal.user_id, PlanInviteStatus.removed
    )


@router.post("/plans/{plan_id}/invites/{invite_id}/block", response_model=schemas.PlanView)
def block_invite(
    plan_id: uuid.UUID, invite_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PlanView:
    return _set_invite_status(
        session, plan_id, invite_id, principal.user_id, PlanInviteStatus.blocked
    )


@router.post("/plans/{plan_id}/confirm", response_model=schemas.PlanView)
def confirm_booking(
    plan_id: uuid.UUID, body: schemas.ConfirmIn,
    principal: CurrentPrincipal, session: SessionDep, gateway: GatewayDep,
    email_gateway: EmailGatewayDep,
) -> schemas.PlanView:
    try:
        _plan, booking, intent = service.confirm_booking(
            session, plan_id=plan_id, actor_id=principal.user_id, gateway=gateway,
            option_id=body.option_id, headcount=body.headcount, email_gateway=email_gateway,
        )
    except Exception as exc:
        raise _map_host_error(exc) from exc
    view = _host_plan(session, plan_id, principal.user_id)
    view.deposit_client_secret = intent.client_secret
    view.deposit_payment_id = booking.deposit_payment_id
    view.deposit_cents = booking.deposit_cents
    return view


# --- Public (tokenized, no auth) -------------------------------------------


@router.get("/public/{plan_token}", response_model=schemas.PublicPlanView)
def public_plan(plan_token: str, session: SessionDep) -> schemas.PublicPlanView:
    plan = service.get_plan_by_token(session, plan_token)
    if plan is None:
        raise _GENERIC_404
    return service.public_plan_view(session, plan)


@router.post(
    "/public/{plan_token}/rsvp",
    status_code=status.HTTP_201_CREATED, response_model=schemas.InviteCreatedOut,
)
def open_rsvp(
    plan_token: str, body: schemas.OpenRsvpIn, request: Request, session: SessionDep,
) -> schemas.InviteCreatedOut:
    # Honeypot: silently accept-and-drop bot submissions with a plausible (unpersisted) receipt.
    # The status mirrors a real auto-approved RSVP so the drop is indistinguishable from success.
    if body.website:
        return schemas.InviteCreatedOut(invite_token=service._token(), status="approved")
    plan = service.get_plan_by_token(session, plan_token)
    if plan is None:
        raise _GENERIC_404
    try:
        service.rate_limit(session, scope_key=f"ip:{_client_ip(request)}")
        service.rate_limit(session, scope_key=f"plan:{plan_token}")
        invite = service.open_rsvp(
            session, plan=plan, parent_name=body.parent_name, email=body.email,
            attending=body.attending, kid_count=body.kid_count, nickname=body.nickname,
            avatar_key=body.avatar_key, marketing_opt_in=body.marketing_opt_in,
        )
    except service.RateLimited as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests") from exc
    except service.RsvpClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "RSVPs are closed") from exc
    return schemas.InviteCreatedOut(invite_token=invite.token, status=invite.status.value)


@router.get("/invite/{invite_token}", response_model=schemas.InviteSelfView)
def invite_self(invite_token: str, session: SessionDep) -> schemas.InviteSelfView:
    invite = service.get_invite_by_token(session, invite_token)
    if invite is None:
        raise _GENERIC_404
    return service.invite_self_view(session, invite)


@router.put("/invite/{invite_token}/rsvp", response_model=schemas.InviteSelfView)
def edit_rsvp(
    invite_token: str, body: schemas.EditRsvpIn, request: Request, session: SessionDep
) -> schemas.InviteSelfView:
    invite = service.get_invite_by_token(session, invite_token)
    if invite is None:
        raise _GENERIC_404
    plan = service.get_plan(session, invite.plan_id)
    if plan is None:
        raise _GENERIC_404
    try:
        service.rate_limit(session, scope_key=f"ip:{_client_ip(request)}")
        service.rate_limit(session, scope_key=f"invite:{invite_token}")
        service.edit_rsvp(
            session, invite=invite, plan=plan, attending=body.attending,
            kid_count=body.kid_count, nickname=body.nickname, avatar_key=body.avatar_key,
        )
    except service.RateLimited as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests") from exc
    except service.RsvpClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "RSVPs are closed") from exc
    return service.invite_self_view(session, invite)


@router.put("/invite/{invite_token}/vote", response_model=schemas.InviteSelfView)
def cast_vote(
    invite_token: str, body: schemas.VoteIn, request: Request, session: SessionDep
) -> schemas.InviteSelfView:
    invite = service.get_invite_by_token(session, invite_token)
    if invite is None:
        raise _GENERIC_404
    try:
        service.rate_limit(session, scope_key=f"ip:{_client_ip(request)}")
        service.rate_limit(session, scope_key=f"invite:{invite_token}")
        service.cast_vote(session, invite=invite, option_id=body.option_id)
    except service.RateLimited as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests") from exc
    except service.RsvpClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Voting is closed") from exc
    except service.InviteNotApproved as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Awaiting host approval") from exc
    except service.OptionNotEligible as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "That option can't be voted for") from exc
    return service.invite_self_view(session, invite)


@router.put("/invite/{invite_token}/react", response_model=schemas.InviteSelfView)
def react(
    invite_token: str, body: schemas.ReactIn, request: Request, session: SessionDep
) -> schemas.InviteSelfView:
    invite = service.get_invite_by_token(session, invite_token)
    if invite is None:
        raise _GENERIC_404
    try:
        service.rate_limit(session, scope_key=f"ip:{_client_ip(request)}")
        service.rate_limit(session, scope_key=f"invite:{invite_token}")
        service.react(session, invite=invite, option_id=body.option_id, emoji=body.emoji)
    except service.RateLimited as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests") from exc
    except service.RsvpClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Reactions are closed") from exc
    except service.InviteNotApproved as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Awaiting host approval") from exc
    except (service.OptionNotEligible, service.InvalidReaction) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid reaction") from exc
    return service.invite_self_view(session, invite)
