"""Strict editor documents and mappings to tutorial authoring domain values."""

from typing import Literal, Self

from pydantic import Field, model_validator

from guojing.application.tutorials.dto import (
    AppIdentityDto,
    ScreenAnchorDto,
    TutorialDto,
    TutorialNodeDto,
    TutorialTransitionDto,
)
from guojing.domain.tutorials.authoring import (
    AnchorCandidate,
    CandidateSource,
    CaptureArtifactKind,
    CaptureArtifactReference,
    CaptureSharingPolicy,
    DraftTutorialGraph,
    ReviewDecision,
    ScreenCapture,
    TutorialDraftDocument,
)


class CaptureArtifactReferenceDto(TutorialDto):
    artifact_id: str = Field(min_length=1)
    kind: CaptureArtifactKind
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def to_domain(self) -> CaptureArtifactReference:
        return CaptureArtifactReference(
            artifact_id=self.artifact_id,
            kind=self.kind,
            sha256=self.sha256,
        )

    @classmethod
    def from_domain(cls, value: CaptureArtifactReference) -> Self:
        return cls(
            artifact_id=value.artifact_id,
            kind=value.kind,
            sha256=value.sha256,
        )


class AnchorCandidateDto(TutorialDto):
    candidate_id: str = Field(min_length=1)
    source: CandidateSource
    suggested_anchor: ScreenAnchorDto
    decision: ReviewDecision = ReviewDecision.PROPOSED
    reviewed_by: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_review_decision(self) -> Self:
        if self.decision is ReviewDecision.PROPOSED and self.reviewed_by is not None:
            raise ValueError("a proposed candidate must not have a reviewer")
        if self.decision is not ReviewDecision.PROPOSED and self.reviewed_by is None:
            raise ValueError("an accepted or rejected candidate needs an admin reviewer")
        return self

    def to_domain(self) -> AnchorCandidate:
        return AnchorCandidate(
            candidate_id=self.candidate_id,
            source=self.source,
            suggested_anchor=self.suggested_anchor.to_domain(),
            decision=self.decision,
            reviewed_by=self.reviewed_by,
        )

    @classmethod
    def from_domain(cls, value: AnchorCandidate) -> Self:
        return cls(
            candidate_id=value.candidate_id,
            source=value.source,
            suggested_anchor=ScreenAnchorDto.from_domain(value.suggested_anchor),
            decision=value.decision,
            reviewed_by=value.reviewed_by,
        )


class ScreenCaptureDto(TutorialDto):
    capture_id: str = Field(min_length=1)
    sharing_policy: CaptureSharingPolicy
    artifacts: tuple[CaptureArtifactReferenceDto, ...] = ()
    candidates: tuple[AnchorCandidateDto, ...] = ()

    @model_validator(mode="after")
    def keep_local_capture_content_off_backend(self) -> Self:
        if self.sharing_policy is CaptureSharingPolicy.LOCAL_ONLY and (
            self.artifacts or self.candidates
        ):
            raise ValueError(
                "local-only captures must not send artifacts or candidate content to the backend"
            )
        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("artifact_id values must be unique")
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate_id values must be unique")
        return self

    def to_domain(self) -> ScreenCapture:
        return ScreenCapture(
            capture_id=self.capture_id,
            sharing_policy=self.sharing_policy,
            artifacts=tuple(artifact.to_domain() for artifact in self.artifacts),
            candidates=tuple(candidate.to_domain() for candidate in self.candidates),
        )

    @classmethod
    def from_domain(cls, value: ScreenCapture) -> Self:
        return cls(
            capture_id=value.capture_id,
            sharing_policy=value.sharing_policy,
            artifacts=tuple(
                CaptureArtifactReferenceDto.from_domain(artifact) for artifact in value.artifacts
            ),
            candidates=tuple(
                AnchorCandidateDto.from_domain(candidate) for candidate in value.candidates
            ),
        )


class DraftTutorialGraphDto(TutorialDto):
    graph_id: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1)
    recorded_app: AppIdentityDto | None = None
    start_node_id: str | None = Field(default=None, min_length=1)
    nodes: tuple[TutorialNodeDto, ...] = ()
    transitions: tuple[TutorialTransitionDto, ...] = ()

    def to_domain(self) -> DraftTutorialGraph:
        return DraftTutorialGraph(
            graph_id=self.graph_id,
            title=self.title,
            recorded_app=(self.recorded_app.to_domain() if self.recorded_app is not None else None),
            start_node_id=self.start_node_id,
            nodes=tuple(node.to_domain() for node in self.nodes),
            transitions=tuple(transition.to_domain() for transition in self.transitions),
        )

    @classmethod
    def from_domain(cls, value: DraftTutorialGraph) -> Self:
        return cls(
            graph_id=value.graph_id,
            title=value.title,
            recorded_app=(
                AppIdentityDto.from_domain(value.recorded_app)
                if value.recorded_app is not None
                else None
            ),
            start_node_id=value.start_node_id,
            nodes=tuple(TutorialNodeDto.from_domain(node) for node in value.nodes),
            transitions=tuple(
                TutorialTransitionDto.from_domain(transition) for transition in value.transitions
            ),
        )


class TutorialDraftDocumentDto(TutorialDto):
    """Versioned editor format; unlike TutorialGraphDto it may be incomplete."""

    schema_version: Literal["1.0"] = "1.0"
    graph: DraftTutorialGraphDto = Field(default_factory=DraftTutorialGraphDto)
    captures: tuple[ScreenCaptureDto, ...] = ()

    @model_validator(mode="after")
    def require_unique_capture_ids(self) -> Self:
        capture_ids = [capture.capture_id for capture in self.captures]
        if len(capture_ids) != len(set(capture_ids)):
            raise ValueError("capture_id values must be unique")
        return self

    def to_domain(self) -> TutorialDraftDocument:
        return TutorialDraftDocument(
            graph=self.graph.to_domain(),
            captures=tuple(capture.to_domain() for capture in self.captures),
        )

    @classmethod
    def from_domain(cls, value: TutorialDraftDocument) -> Self:
        return cls(
            graph=DraftTutorialGraphDto.from_domain(value.graph),
            captures=tuple(ScreenCaptureDto.from_domain(capture) for capture in value.captures),
        )
