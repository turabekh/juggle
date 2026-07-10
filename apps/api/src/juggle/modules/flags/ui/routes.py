"""HTTP routes for the flags module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/flags", tags=["flags"])
