"""HTTP adapter for tutorial authoring, publication, and Android reads."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from guojing.api.dependencies import get_tutorial_service, require_admin
from guojing.application.tutorials.dto import TutorialGraphDto
from guojing.application.tutorials.models import (
    PublishedTutorial,
    PublishedTutorialSummary,
    TutorialRevision,
)
from guojing.application.tutorials.ports import (
    TutorialIdentityConflictError,
    TutorialNotFoundError,
)
from guojing.application.tutorials.service import TutorialService
from guojing.domain.tutorials.validation import InvalidTutorialGraph

router = APIRouter(prefix="/api/v1", tags=["tutorials"])
TutorialServiceDependency = Annotated[TutorialService, Depends(get_tutorial_service)]
AdminDependency = Annotated[None, Depends(require_admin)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TutorialRevisionResponse(ApiModel):
    graph_id: str
    revision_number: int
    created_at: datetime

    @classmethod
    def from_application(cls, value: TutorialRevision) -> "TutorialRevisionResponse":
        return cls(
            graph_id=value.graph.graph_id,
            revision_number=value.revision_number,
            created_at=value.created_at,
        )


class PublishedTutorialSummaryResponse(ApiModel):
    graph_id: str
    title: str
    package_name: str
    recorded_version_name: str
    recorded_version_code: int
    revision_number: int
    published_at: datetime

    @classmethod
    def from_application(
        cls,
        value: PublishedTutorialSummary,
    ) -> "PublishedTutorialSummaryResponse":
        return cls(
            graph_id=value.graph_id,
            title=value.title,
            package_name=value.package_name,
            recorded_version_name=value.recorded_version_name,
            recorded_version_code=value.recorded_version_code,
            revision_number=value.revision_number,
            published_at=value.published_at,
        )


class PublishedTutorialResponse(ApiModel):
    revision_number: int
    published_at: datetime
    graph: TutorialGraphDto

    @classmethod
    def from_application(cls, value: PublishedTutorial) -> "PublishedTutorialResponse":
        return cls(
            revision_number=value.revision_number,
            published_at=value.published_at,
            graph=TutorialGraphDto.from_domain(value.graph),
        )


@router.post(
    "/admin/tutorials/drafts",
    response_model=TutorialRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tutorial_draft(
    graph: TutorialGraphDto,
    service: TutorialServiceDependency,
    _admin: AdminDependency,
) -> TutorialRevisionResponse:
    """Validate and append one immutable tutorial revision."""
    try:
        revision = service.save_draft(graph.to_domain())
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    return TutorialRevisionResponse.from_application(revision)


@router.post(
    "/admin/tutorials/{graph_id}/revisions/{revision_number}/publish",
    response_model=PublishedTutorialResponse,
)
def publish_tutorial_revision(
    graph_id: str,
    revision_number: int,
    service: TutorialServiceDependency,
    _admin: AdminDependency,
) -> PublishedTutorialResponse:
    """Move the public pointer to one explicit revision."""
    try:
        published = service.publish(graph_id, revision_number)
    except (TutorialNotFoundError, ValueError) as error:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if isinstance(error, TutorialNotFoundError)
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return PublishedTutorialResponse.from_application(published)


@router.get("/tutorials", response_model=list[PublishedTutorialSummaryResponse])
def list_published_tutorials(
    service: TutorialServiceDependency,
) -> list[PublishedTutorialSummaryResponse]:
    """List only revisions approved for Android clients."""
    return [
        PublishedTutorialSummaryResponse.from_application(summary)
        for summary in service.list_published()
    ]


@router.get("/tutorials/{graph_id}", response_model=PublishedTutorialResponse)
def get_published_tutorial(
    graph_id: str,
    service: TutorialServiceDependency,
) -> PublishedTutorialResponse:
    """Read one currently published tutorial graph."""
    try:
        published = service.get_published(graph_id)
    except TutorialNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return PublishedTutorialResponse.from_application(published)
