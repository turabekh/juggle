"""HTTP routes for the notifications module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/notifications", tags=["notifications"])
