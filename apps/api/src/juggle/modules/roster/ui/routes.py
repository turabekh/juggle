"""HTTP routes for the roster module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/roster", tags=["roster"])
