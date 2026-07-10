"""HTTP routes for the inventory module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/inventory", tags=["inventory"])
