"""FastAPI application entry point."""

from fastapi import FastAPI

from guojing.api.router import api_router
from guojing.core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an isolated application instance for production or tests."""
    app_settings = settings or Settings()
    application = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.debug,
    )
    application.state.settings = app_settings
    application.include_router(api_router)
    return application


app = create_app()
