"""HTTP routes for the audit module. Endpoints land during feature milestones."""

from fastapi import APIRouter

router = APIRouter(prefix="/audit", tags=["audit"])
