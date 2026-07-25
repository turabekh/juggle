"""Web layer (FastAPI routers) for the parties module."""

from juggle.modules.parties.ui.quote_routes import router as quote_router
from juggle.modules.parties.ui.routes import router

__all__ = ["quote_router", "router"]
