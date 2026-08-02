"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from guojing.api.router import api_router
from guojing.application.tutorials.service import TutorialService
from guojing.core.config import Settings
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.tutorial_repository import (
    SqlAlchemyTutorialRepository,
)


def create_app(
    settings: Settings | None = None,
    tutorial_service: TutorialService | None = None,
) -> FastAPI:
    """Build an isolated application instance for production or tests."""
    app_settings = settings or Settings()
    database: Database | None = None
    if tutorial_service is None:
        database = Database(app_settings.database_url)
        tutorial_service = TutorialService(SqlAlchemyTutorialRepository(database))

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        yield
        if database is not None:
            database.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.debug,
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.tutorial_service = tutorial_service
    application.include_router(api_router)
    return application


app = create_app()
