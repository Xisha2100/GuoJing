"""HTTP login and logout adapter for the management webpage."""

from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from guojing.api.dependencies import (
    get_admin_auth_service,
    require_admin,
    require_admin_session,
)
from guojing.application.auth.ports import (
    AdminLoginRateLimitedError,
    InvalidAdminCredentialsError,
)
from guojing.application.auth.service import AdminAuthService
from guojing.core.config import Settings
from guojing.core.security import (
    ADMIN_CSRF_COOKIE,
    ADMIN_CSRF_COOKIE_PATH,
    ADMIN_SESSION_COOKIE,
    ADMIN_SESSION_COOKIE_PATH,
)
from guojing.domain.auth import AuthenticatedAdminSession

router = APIRouter(prefix="/api/v1/admin/auth", tags=["admin authentication"])
AuthServiceDependency = Annotated[AdminAuthService, Depends(get_admin_auth_service)]
AdminSessionDependency = Annotated[
    AuthenticatedAdminSession,
    Depends(require_admin_session),
]
AdminMutationDependency = Annotated[AuthenticatedAdminSession, Depends(require_admin)]


class AuthApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(AuthApiModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class AdminSessionResponse(AuthApiModel):
    user_id: str
    username: str
    expires_at: datetime

    @classmethod
    def from_context(cls, value: AuthenticatedAdminSession) -> "AdminSessionResponse":
        return cls(
            user_id=value.admin.user_id,
            username=value.admin.username,
            expires_at=value.expires_at,
        )


@router.post("/login", response_model=AdminSessionResponse)
def login_admin(
    login: LoginRequest,
    response: Response,
    request: Request,
    auth_service: AuthServiceDependency,
) -> AdminSessionResponse:
    try:
        grant = auth_service.login(login.username, login.password)
    except (InvalidAdminCredentialsError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid username or password",
        ) from error
    except AdminLoginRateLimitedError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(error),
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error

    settings = cast(Settings, request.app.state.settings)
    max_age = int((grant.context.expires_at - grant.context.created_at).total_seconds())
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        grant.session_token,
        max_age=max_age,
        path=ADMIN_SESSION_COOKIE_PATH,
        secure=settings.admin_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        ADMIN_CSRF_COOKIE,
        grant.csrf_token,
        max_age=max_age,
        path=ADMIN_CSRF_COOKIE_PATH,
        secure=settings.admin_cookie_secure,
        httponly=False,
        samesite="strict",
    )
    return AdminSessionResponse.from_context(grant.context)


@router.get("/me", response_model=AdminSessionResponse)
def get_current_admin(context: AdminSessionDependency) -> AdminSessionResponse:
    return AdminSessionResponse.from_context(context)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_admin(
    response: Response,
    context: AdminMutationDependency,
    auth_service: AuthServiceDependency,
) -> None:
    auth_service.logout(context)
    response.delete_cookie(ADMIN_SESSION_COOKIE, path=ADMIN_SESSION_COOKIE_PATH)
    response.delete_cookie(ADMIN_CSRF_COOKIE, path=ADMIN_CSRF_COOKIE_PATH)
