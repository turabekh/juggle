"""Pydantic schemas for the scheduler module."""

from pydantic import BaseModel


class JobSummary(BaseModel):
    """What one maintenance tick did — returned by the worker and the admin run."""

    holds_reclaimed: int
    waitlist_sessions_processed: int
    waitlist_offers_made: int
    waitlist_offers_expired: int
    reminders_sent: int
    what_to_bring_sent: int
    compliance_expired: int
