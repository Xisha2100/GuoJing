"""HTTP adapter for incremental tutorial recording and editing."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from guojing.api.dependencies import (
    get_admin_auth_service,
    get_tutorial_draft_service,
    require_admin,
    require_admin_session,
)
from guojing.application.auth.service import AdminAuthService
from guojing.application.tutorial_drafts.dto import TutorialDraftDocumentDto
from guojing.application.tutorial_drafts.models import (
    DraftPromotion,
    DraftReadiness,
    TutorialDraftWorkspaceSummary,
)
from guojing.application.tutorial_drafts.ports import (
    TutorialDraftVersionConflictError,
    TutorialDraftWorkspaceNotFoundError,
)
from guojing.application.tutorial_drafts.service import TutorialDraftService
from guojing.application.tutorials.ports import TutorialIdentityConflictError
from guojing.application.tutorials.templates import TutorialTemplateCatalog
from guojing.domain.auth import AuthenticatedAdminSession
from guojing.domain.tutorials.authoring import (
    IncompleteTutorialDraft,
    TutorialDraftWorkspace,
)
from guojing.domain.tutorials.validation import InvalidTutorialGraph

router = APIRouter(prefix="/api/v1/admin/tutorial-drafts", tags=["tutorial authoring"])
DraftServiceDependency = Annotated[TutorialDraftService, Depends(get_tutorial_draft_service)]
AuthServiceDependency = Annotated[AdminAuthService, Depends(get_admin_auth_service)]
AdminSessionDependency = Annotated[
    AuthenticatedAdminSession,
    Depends(require_admin_session),
]
AdminMutationDependency = Annotated[AuthenticatedAdminSession, Depends(require_admin)]


class AuthoringApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateWorkspaceRequest(AuthoringApiModel):
    document: TutorialDraftDocumentDto = Field(default_factory=TutorialDraftDocumentDto)


class ReplaceWorkspaceRequest(AuthoringApiModel):
    expected_version: int = Field(ge=1)
    document: TutorialDraftDocumentDto


class PromoteWorkspaceRequest(AuthoringApiModel):
    expected_version: int = Field(ge=1)


class WorkspaceResponse(AuthoringApiModel):
    workspace_id: str
    version: int
    document: TutorialDraftDocumentDto
    created_at: datetime
    updated_at: datetime
    promoted_graph_id: str | None
    promoted_revision_number: int | None

    @classmethod
    def from_domain(cls, value: TutorialDraftWorkspace) -> "WorkspaceResponse":
        return cls(
            workspace_id=value.workspace_id,
            version=value.version,
            document=TutorialDraftDocumentDto.from_domain(value.document),
            created_at=value.created_at,
            updated_at=value.updated_at,
            promoted_graph_id=value.promoted_graph_id,
            promoted_revision_number=value.promoted_revision_number,
        )


class WorkspaceSummaryResponse(AuthoringApiModel):
    workspace_id: str
    version: int
    graph_id: str | None
    title: str | None
    updated_at: datetime
    promoted_graph_id: str | None
    promoted_revision_number: int | None

    @classmethod
    def from_application(
        cls,
        value: TutorialDraftWorkspaceSummary,
    ) -> "WorkspaceSummaryResponse":
        return cls(
            workspace_id=value.workspace_id,
            version=value.version,
            graph_id=value.graph_id,
            title=value.title,
            updated_at=value.updated_at,
            promoted_graph_id=value.promoted_graph_id,
            promoted_revision_number=value.promoted_revision_number,
        )


class ReadinessIssueResponse(AuthoringApiModel):
    code: str
    message: str
    path: str | None = None
    node_id: str | None = None
    transition_id: str | None = None


class ReadinessResponse(AuthoringApiModel):
    workspace_id: str
    version: int
    ready: bool
    issues: tuple[ReadinessIssueResponse, ...]

    @classmethod
    def from_application(
        cls,
        workspace: TutorialDraftWorkspace,
        readiness: DraftReadiness,
    ) -> "ReadinessResponse":
        return cls(
            workspace_id=workspace.workspace_id,
            version=workspace.version,
            ready=readiness.ready,
            issues=tuple(
                ReadinessIssueResponse(
                    code=issue.code,
                    message=issue.message,
                    path=issue.path,
                    node_id=issue.node_id,
                    transition_id=issue.transition_id,
                )
                for issue in readiness.issues
            ),
        )


class PromotionResponse(AuthoringApiModel):
    workspace: WorkspaceResponse
    graph_id: str
    revision_number: int
    created_at: datetime

    @classmethod
    def from_application(cls, value: DraftPromotion) -> "PromotionResponse":
        return cls(
            workspace=WorkspaceResponse.from_domain(value.workspace),
            graph_id=value.revision.graph.graph_id,
            revision_number=value.revision.revision_number,
            created_at=value.revision.created_at,
        )


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    request: CreateWorkspaceRequest,
    service: DraftServiceDependency,
    admin: AdminMutationDependency,
    auth_service: AuthServiceDependency,
) -> WorkspaceResponse:
    auth_service.record_action(
        admin,
        "tutorial_workspace.create_requested",
        "tutorial_draft_workspace",
        None,
    )
    workspace = service.create(request.document.to_domain())
    return WorkspaceResponse.from_domain(workspace)


@router.post(
    "/from-template/{template_id}",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_workspace_from_template(
    template_id: str,
    service: DraftServiceDependency,
    admin: AdminMutationDependency,
    auth_service: AuthServiceDependency,
) -> WorkspaceResponse:
    """Import a reviewed starter into an editable draft, never directly to publication."""
    try:
        document = TutorialTemplateCatalog().create_document(template_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    auth_service.record_action(
        admin,
        "tutorial_workspace.template_import_requested",
        "tutorial_draft_workspace",
        None,
        {"template_id": template_id},
    )
    return WorkspaceResponse.from_domain(service.create(document))


@router.get("", response_model=list[WorkspaceSummaryResponse])
def list_workspaces(
    service: DraftServiceDependency,
    _admin: AdminSessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[WorkspaceSummaryResponse]:
    return [
        WorkspaceSummaryResponse.from_application(summary) for summary in service.list_recent(limit)
    ]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: str,
    service: DraftServiceDependency,
    _admin: AdminSessionDependency,
) -> WorkspaceResponse:
    try:
        return WorkspaceResponse.from_domain(service.get(workspace_id))
    except TutorialDraftWorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
def replace_workspace(
    workspace_id: str,
    request: ReplaceWorkspaceRequest,
    service: DraftServiceDependency,
    admin: AdminMutationDependency,
    auth_service: AuthServiceDependency,
) -> WorkspaceResponse:
    auth_service.record_action(
        admin,
        "tutorial_workspace.replace_requested",
        "tutorial_draft_workspace",
        workspace_id,
        {"expected_version": request.expected_version},
    )
    try:
        workspace = service.replace(
            workspace_id,
            request.expected_version,
            request.document.to_domain(),
        )
    except TutorialDraftWorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except TutorialDraftVersionConflictError as error:
        raise _version_conflict(error) from error
    return WorkspaceResponse.from_domain(workspace)


@router.post("/{workspace_id}/validate", response_model=ReadinessResponse)
def validate_workspace(
    workspace_id: str,
    service: DraftServiceDependency,
    _admin: AdminMutationDependency,
) -> ReadinessResponse:
    try:
        workspace = service.get(workspace_id)
    except TutorialDraftWorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return ReadinessResponse.from_application(
        workspace,
        service.validate(workspace.document),
    )


@router.post("/{workspace_id}/promote", response_model=PromotionResponse)
def promote_workspace(
    workspace_id: str,
    request: PromoteWorkspaceRequest,
    service: DraftServiceDependency,
    admin: AdminMutationDependency,
    auth_service: AuthServiceDependency,
) -> PromotionResponse:
    auth_service.record_action(
        admin,
        "tutorial_workspace.promote_requested",
        "tutorial_draft_workspace",
        workspace_id,
        {"expected_version": request.expected_version},
    )
    try:
        promotion = service.promote(workspace_id, request.expected_version)
    except TutorialDraftWorkspaceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except TutorialDraftVersionConflictError as error:
        raise _version_conflict(error) from error
    except IncompleteTutorialDraft as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "code": issue.code.value,
                    "message": issue.message,
                    "path": issue.path,
                }
                for issue in error.issues
            ],
        ) from error
    except InvalidTutorialGraph as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "code": issue.code.value,
                    "message": issue.message,
                    "node_id": issue.node_id,
                    "transition_id": issue.transition_id,
                }
                for issue in error.issues
            ],
        ) from error
    except TutorialIdentityConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return PromotionResponse.from_application(promotion)


def _version_conflict(error: TutorialDraftVersionConflictError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "workspace_version_conflict",
            "message": str(error),
            "expected_version": error.expected_version,
            "current_version": error.current_version,
        },
    )
