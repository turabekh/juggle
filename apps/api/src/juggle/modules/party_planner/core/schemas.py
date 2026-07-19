"""Pydantic schemas for the Party Planner (ADR-0011).

Response models are deliberately PII-lean: the public + invitee views never carry child data
(INV-3) and never expose vote-by-invite (INV-13) — only aggregate tallies and a self ``has_voted``
boolean. Host views may include guest emails (the host's own transactional data) but never votes.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# --- Requests --------------------------------------------------------------


class CreatePlanIn(BaseModel):
    theme: str = Field(default="default", max_length=40)


class AddPackageOptionIn(BaseModel):
    package_id: uuid.UUID
    slot_id: uuid.UUID


class AddCustomOptionIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class RankingIn(BaseModel):
    option_ids: list[uuid.UUID] = Field(max_length=4)


class DeadlineIn(BaseModel):
    deadline_at: datetime


class EmailInviteIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)


class EmailInvitesIn(BaseModel):
    invites: list[EmailInviteIn] = Field(min_length=1, max_length=100)


class ConfirmIn(BaseModel):
    option_id: uuid.UUID | None = None  # override; defaults to the winner
    headcount: int | None = Field(default=None, ge=1)  # override; defaults to Σ yes-RSVP


class OpenRsvpIn(BaseModel):
    parent_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    attending: bool
    kid_count: int = Field(ge=0, le=50)
    nickname: str | None = Field(default=None, max_length=80)
    avatar_key: str | None = Field(default=None, max_length=40)
    marketing_opt_in: bool = False
    website: str = ""  # honeypot — real users never fill this


class EditRsvpIn(BaseModel):
    attending: bool
    kid_count: int = Field(ge=0, le=50)
    nickname: str | None = Field(default=None, max_length=80)
    avatar_key: str | None = Field(default=None, max_length=40)


class VoteIn(BaseModel):
    option_id: uuid.UUID


class ThemeIn(BaseModel):
    theme: str = Field(max_length=40)


class PagePatchIn(BaseModel):
    """Full-state update of the party page. The editor holds all fields and sends them together;
    title/message are untrusted host text (sanitised server-side), template/hero_avatar/widgets are
    validated against closed allow-lists."""

    template: str = Field(default="default", max_length=40)
    title: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=2000)
    hero_avatar: str | None = Field(default=None, max_length=40)
    widgets: list[str] = Field(default_factory=list, max_length=16)


class ReactIn(BaseModel):
    option_id: uuid.UUID
    emoji: str = Field(max_length=16)


# --- Responses -------------------------------------------------------------


class OptionView(BaseModel):
    id: uuid.UUID
    kind: str
    position: int
    voided: bool
    custom_text: str | None = None
    # Package options only:
    package_id: uuid.UUID | None = None
    package_name: str | None = None
    venue_name: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    per_head_price_cents: int | None = None
    available: bool | None = None  # live inventory (INV-12); None for custom options
    votes: int = 0
    is_favourite: bool = False  # ⭐ birthday kid's top-ranked non-voided option
    reactions: dict[str, int] = {}  # emoji → count (aggregate, unattributed)


class PartyPageView(BaseModel):
    """Host-customizable party page config, echoed to both host + public views. All pseudonymous:
    a parent-chosen title/nickname + a sticker avatar + a template + enabled widget keys — never
    child PII (INV-3/INV-13)."""

    template: str
    title: str | None
    message: str | None
    hero_avatar: str | None
    widgets: list[str]


class BoardEntry(BaseModel):
    nickname: str | None
    avatar_key: str | None


class HostInviteView(BaseModel):
    id: uuid.UUID
    mode: str
    parent_name: str
    email: str
    status: str
    attending: bool | None = None
    kid_count: int | None = None
    nickname: str | None = None
    avatar_key: str | None = None


class PlanView(BaseModel):
    """Host-facing view — includes the approval queue + board, never votes-by-invite."""

    id: uuid.UUID
    status: str
    deadline_at: datetime | None
    theme: str
    approval_required: bool
    share_token: str | None
    share_path: str | None
    winning_option_id: uuid.UUID | None
    booking_id: uuid.UUID | None
    ranking: list[uuid.UUID]
    options: list[OptionView]
    invites: list[HostInviteView]
    rsvp_yes_headcount: int
    page: PartyPageView
    deadline_warnings: list[str] = []
    # Transient — populated only by the confirm response so the host can settle the deposit
    # (live: mount the Payment Element; dev: dev-confirm the booking).
    deposit_client_secret: str | None = None
    deposit_payment_id: uuid.UUID | None = None
    deposit_cents: int | None = None


class PublicPlanView(BaseModel):
    """Invitee-facing view — pseudonymous board + aggregate tallies; no child/PII, no vote-by-invite."""  # noqa: E501

    status: str
    is_open: bool
    deadline_at: datetime | None
    theme: str
    options: list[OptionView]
    board: list[BoardEntry]
    rsvp_count: int
    page: PartyPageView
    winner_option_id: uuid.UUID | None = None
    is_tie: bool = False


class InviteCreatedOut(BaseModel):
    invite_token: str
    status: str


class RsvpView(BaseModel):
    attending: bool
    kid_count: int
    nickname: str | None
    avatar_key: str | None


class InviteSelfView(BaseModel):
    """What an invitee sees via their own capability token. ``has_voted`` is a boolean only — the
    chosen option is never returned (honours 'no API endpoint returns vote-by-invite')."""

    invite_token: str
    status: str
    has_voted: bool
    rsvp: RsvpView | None
    plan: PublicPlanView
