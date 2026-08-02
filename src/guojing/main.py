"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from guojing.api.router import api_router
from guojing.application.tutorial_drafts.service import TutorialDraftService
from guojing.application.tutorials.service import TutorialService
from guojing.core.config import Settings
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.tutorial_draft_repository import (
    SqlAlchemyTutorialDraftRepository,
)
from guojing.infrastructure.persistence.tutorial_repository import (
    SqlAlchemyTutorialRepository,
)


def create_app(
    settings: Settings | None = None,
    tutorial_service: TutorialService | None = None,
    tutorial_draft_service: TutorialDraftService | None = None,
) -> FastAPI:
    """Build an isolated application instance for production or tests."""
    app_settings = settings or Settings()
    database: Database | None = None
    if tutorial_service is None or tutorial_draft_service is None:
        database = Database(app_settings.database_url)
    if tutorial_service is None:
        assert database is not None
        tutorial_service = TutorialService(SqlAlchemyTutorialRepository(database))
    if tutorial_draft_service is None:
        assert database is not None
        tutorial_draft_service = TutorialDraftService(SqlAlchemyTutorialDraftRepository(database))

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
    application.state.tutorial_draft_service = tutorial_draft_service
    application.include_router(api_router)
    return application


app = create_app()
