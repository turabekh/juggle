"""HTTP routes for the booking module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/booking", tags=["booking"])
