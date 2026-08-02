"""FastAPI dependency adapters for application services and admin security."""

from hmac import compare_digest
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from guojing.application.tutorial_drafts.service import TutorialDraftService
from guojing.application.tutorials.service import TutorialService
from guojing.core.config import Settings

_bearer = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def get_tutorial_service(request: Request) -> TutorialService:
    """Return the use-case service installed by the composition root."""
    return cast(TutorialService, request.app.state.tutorial_service)


def get_tutorial_draft_service(request: Request) -> TutorialDraftService:
    """Return the incremental authoring service installed at startup."""
    return cast(TutorialDraftService, request.app.state.tutorial_draft_service)


def require_admin(request: Request, credentials: BearerCredentials) -> None:
    """Protect bootstrap admin writes; disabled is safer than an open endpoint."""
    settings = cast(Settings, request.app.state.settings)
    configured_token = settings.admin_api_token
    if configured_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin API is disabled until GUOJING_ADMIN_API_TOKEN is configured",
        )
    if credentials is None or not compare_digest(
        credentials.credentials,
        configured_token.get_secret_value(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid admin bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
