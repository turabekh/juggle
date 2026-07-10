"""HTTP routes for the identity module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/identity", tags=["identity"])
