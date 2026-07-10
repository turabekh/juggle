"""HTTP routes for the search module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/search", tags=["search"])
