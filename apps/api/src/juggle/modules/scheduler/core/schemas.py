"""Pydantic schemas for the scheduler module."""

from pydantic import BaseModel


class JobSummary(BaseModel):
    """What one maintenance tick did — returned by the worker and the admin run."""

    holds_reclaimed: int
    abandoned_checkouts_swept: int
    party_deposits_swept: int
    party_balances_processed: int
    waitlist_sessions_processed: int
    waitlist_offers_made: int
    waitlist_offers_expired: int
    reminders_sent: int
    what_to_bring_sent: int
    compliance_expired: int
    plans_resolved: int = 0
    plans_swept: int = 0
    plans_purged: int = 0
