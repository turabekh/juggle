"""HTTP routes for the config module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/config", tags=["config"])
