"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI

from guojing.api.router import api_router
from guojing.application.auth.service import AdminAuthService
from guojing.application.help_requests.evidence_service import HelpRequestEvidenceService
from guojing.application.help_requests.service import HelpRequestService
from guojing.application.tutorial_drafts.service import TutorialDraftService
from guojing.application.tutorials.service import TutorialService
from guojing.core.config import Settings
from guojing.infrastructure.persistence.admin_auth_repository import (
    SqlAlchemyAdminAuthRepository,
)
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.help_request_evidence_repository import (
    SqlAlchemyHelpRequestEvidenceRepository,
)
from guojing.infrastructure.persistence.help_request_repository import (
    SqlAlchemyHelpRequestRepository,
)
from guojing.infrastructure.persistence.tutorial_draft_repository import (
    SqlAlchemyTutorialDraftRepository,
)
from guojing.infrastructure.persistence.tutorial_repository import (
    SqlAlchemyTutorialRepository,
)
from guojing.infrastructure.security.passwords import Argon2PasswordHasher


def create_app(
    settings: Settings | None = None,
    tutorial_service: TutorialService | None = None,
    tutorial_draft_service: TutorialDraftService | None = None,
    admin_auth_service: AdminAuthService | None = None,
    help_request_service: HelpRequestService | None = None,
    help_request_evidence_service: HelpRequestEvidenceService | None = None,
) -> FastAPI:
    """Build an isolated application instance for production or tests."""
    app_settings = settings or Settings()
    database: Database | None = None
    if (
        tutorial_service is None
        or tutorial_draft_service is None
        or admin_auth_service is None
        or help_request_service is None
        or help_request_evidence_service is None
    ):
        database = Database(app_settings.database_url)
    if tutorial_service is None:
        assert database is not None
        tutorial_service = TutorialService(SqlAlchemyTutorialRepository(database))
    if tutorial_draft_service is None:
        assert database is not None
        tutorial_draft_service = TutorialDraftService(SqlAlchemyTutorialDraftRepository(database))
    if admin_auth_service is None:
        assert database is not None
        admin_auth_service = AdminAuthService(
            SqlAlchemyAdminAuthRepository(database),
            Argon2PasswordHasher(),
            session_ttl=timedelta(minutes=app_settings.admin_session_ttl_minutes),
            login_window=timedelta(minutes=app_settings.admin_login_window_minutes),
            maximum_failures=app_settings.admin_maximum_login_failures,
        )
    if help_request_service is None:
        assert database is not None
        help_request_service = HelpRequestService(
            repository=SqlAlchemyHelpRequestRepository(database),
        )
    if help_request_evidence_service is None:
        assert database is not None
        assert help_request_service is not None
        help_request_evidence_service = HelpRequestEvidenceService(
            help_request_service,
            SqlAlchemyHelpRequestEvidenceRepository(database),
        )

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
    application.state.admin_auth_service = admin_auth_service
    application.state.help_request_service = help_request_service
    application.state.help_request_evidence_service = help_request_evidence_service
    application.include_router(api_router)
    return application


app = create_app()
