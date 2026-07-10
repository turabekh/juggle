"""HTTP routes for the payments module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/payments", tags=["payments"])
