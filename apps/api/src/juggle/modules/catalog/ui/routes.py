"""HTTP routes for the catalog module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/catalog", tags=["catalog"])
