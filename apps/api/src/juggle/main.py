"""FastAPI application factory for the Juggle API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from juggle import __version__
from juggle.api import api_router
from juggle.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Juggle API",
        version=__version__,
        description=(
            "Kids' holiday-activities & birthday-party booking marketplace "
            "(Perth beachhead). See docs/juggle-prd.md."
        ),
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Liveness probe — no DB dependency."""
        return {"status": "ok", "version": __version__, "environment": settings.environment}

    app.include_router(api_router)

    return app


app = create_app()
