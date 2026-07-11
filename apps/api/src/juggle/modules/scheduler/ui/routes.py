"""HTTP routes for the scheduler module.

A manual trigger for the maintenance tick (admin-gated). A cron/worker normally
drives ``run_due_jobs``; this endpoint lets an operator run it on demand and see
what it did — the same shape the worker logs.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentAdmin
from juggle.modules.scheduler.core import service
from juggle.modules.scheduler.core.schemas import JobSummary

router = APIRouter(prefix="/scheduler", tags=["scheduler"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/run", response_model=JobSummary)
def run_now(admin: CurrentAdmin, session: SessionDep) -> JobSummary:
    return service.run_due_jobs(session, now=datetime.now(UTC))
