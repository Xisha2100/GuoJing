"""FastAPI dependency adapters for application services and admin security."""

from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status

from guojing.application.auth.ports import (
    InvalidAdminSessionError,
    InvalidCsrfTokenError,
)
from guojing.application.auth.service import AdminAuthService
from guojing.application.help_requests.evidence_service import HelpRequestEvidenceService
from guojing.application.help_requests.service import HelpRequestService
from guojing.application.tutorial_drafts.service import TutorialDraftService
from guojing.application.tutorials.service import TutorialService
from guojing.core.security import ADMIN_CSRF_COOKIE, ADMIN_CSRF_HEADER, ADMIN_SESSION_COOKIE
from guojing.domain.auth import AuthenticatedAdminSession

CsrfHeader = Annotated[str | None, Header(alias=ADMIN_CSRF_HEADER)]


def get_admin_auth_service(request: Request) -> AdminAuthService:
    """Return the administrator authentication service installed at startup."""
    return cast(AdminAuthService, request.app.state.admin_auth_service)


def get_tutorial_service(request: Request) -> TutorialService:
    """Return the use-case service installed by the composition root."""
    return cast(TutorialService, request.app.state.tutorial_service)


def get_help_request_service(request: Request) -> HelpRequestService:
    """Return the transient help-request service installed at startup."""
    return cast(HelpRequestService, request.app.state.help_request_service)


def get_help_request_evidence_service(request: Request) -> HelpRequestEvidenceService:
    """Return the evidence service installed at startup."""
    return cast(
        HelpRequestEvidenceService,
        request.app.state.help_request_evidence_service,
    )


def get_tutorial_draft_service(request: Request) -> TutorialDraftService:
    """Return the incremental authoring service installed at startup."""
    return cast(TutorialDraftService, request.app.state.tutorial_draft_service)


def require_admin_session(request: Request) -> AuthenticatedAdminSession:
    """Resolve the opaque HttpOnly cookie through server-side session state."""
    auth_service = get_admin_auth_service(request)
    try:
        return auth_service.authenticate(request.cookies.get(ADMIN_SESSION_COOKIE, ""))
    except InvalidAdminSessionError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="administrator login is required",
        ) from error


AdminContextDependency = Annotated[
    AuthenticatedAdminSession,
    Depends(require_admin_session),
]


def require_admin(
    request: Request,
    context: AdminContextDependency,
    csrf_header: CsrfHeader = None,
) -> AuthenticatedAdminSession:
    """Require a live session plus double-submit CSRF proof for mutations."""
    auth_service = get_admin_auth_service(request)
    try:
        auth_service.require_csrf(
            context,
            request.cookies.get(ADMIN_CSRF_COOKIE, ""),
            csrf_header or "",
        )
    except InvalidCsrfTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="valid CSRF cookie and header are required",
        ) from error
    return context
