"""HTTP routes for the admin module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])
