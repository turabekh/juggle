"""Aggregates every module's router under a single versioned API prefix.

Adding a module = create it under ``juggle.modules`` with a ``ui.router`` and
list it here. Nothing else in the app imports module routers directly.
"""

from fastapi import APIRouter

from juggle.modules.admin.ui import router as admin_router
from juggle.modules.audit.ui import router as audit_router
from juggle.modules.booking.ui import router as booking_router
from juggle.modules.catalog.ui import router as catalog_router
from juggle.modules.config.ui import router as config_router
from juggle.modules.flags.ui import router as flags_router
from juggle.modules.identity.ui import router as identity_router
from juggle.modules.inventory.ui import router as inventory_router
from juggle.modules.notifications.ui import router as notifications_router
from juggle.modules.org.ui import router as org_router
from juggle.modules.payments.ui import router as payments_router
from juggle.modules.reviews.ui import router as reviews_router
from juggle.modules.roster.ui import router as roster_router
from juggle.modules.search.ui import router as search_router

api_router = APIRouter(prefix="/api/v1")

for _router in (
    identity_router,
    org_router,
    catalog_router,
    inventory_router,
    booking_router,
    payments_router,
    reviews_router,
    roster_router,
    notifications_router,
    search_router,
    admin_router,
    config_router,
    flags_router,
    audit_router,
):
    api_router.include_router(_router)
