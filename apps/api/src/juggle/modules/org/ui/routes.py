"""HTTP routes for the org module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/org", tags=["org"])
