"""Versioned transport models and explicit tutorial domain mappings."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guojing.domain.tutorials.models import (
    ActionKind,
    AnchorRole,
    AppIdentity,
    NormalizedBounds,
    PrivacyMode,
    RelativeConstraint,
    RelativePosition,
    RiskLevel,
    ScreenAnchor,
    SemanticLocator,
    TutorialGraph,
    TutorialNode,
    TutorialTransition,
    VerificationStatus,
)


class TutorialDto(BaseModel):
    """Strict base model for persisted and HTTP tutorial documents."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AppIdentityDto(TutorialDto):
    package_name: str = Field(min_length=1, max_length=255)
    version_name: str = Field(min_length=1, max_length=120)
    version_code: int = Field(ge=1)

    def to_domain(self) -> AppIdentity:
        return AppIdentity(**self.model_dump())

    @classmethod
    def from_domain(cls, value: AppIdentity) -> Self:
        return cls(
            package_name=value.package_name,
            version_name=value.version_name,
            version_code=value.version_code,
        )


class NormalizedBoundsDto(TutorialDto):
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_rectangle(self) -> Self:
        if self.left >= self.right:
            raise ValueError("left must be smaller than right")
        if self.top >= self.bottom:
            raise ValueError("top must be smaller than bottom")
        return self

    def to_domain(self) -> NormalizedBounds:
        return NormalizedBounds(**self.model_dump())

    @classmethod
    def from_domain(cls, value: NormalizedBounds) -> Self:
        return cls(left=value.left, top=value.top, right=value.right, bottom=value.bottom)


class SemanticLocatorDto(TutorialDto):
    resource_id: str | None = Field(default=None, min_length=1)
    content_description: str | None = Field(default=None, min_length=1)
    text: str | None = Field(default=None, min_length=1)
    ocr_text: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_one_locator(self) -> Self:
        if not any(
            value
            for value in (
                self.resource_id,
                self.content_description,
                self.text,
                self.ocr_text,
            )
        ):
            raise ValueError("a semantic locator needs at least one non-blank value")
        return self

    def to_domain(self) -> SemanticLocator:
        return SemanticLocator(**self.model_dump())

    @classmethod
    def from_domain(cls, value: SemanticLocator) -> Self:
        return cls(
            resource_id=value.resource_id,
            content_description=value.content_description,
            text=value.text,
            ocr_text=value.ocr_text,
        )


class RelativeConstraintDto(TutorialDto):
    reference_anchor_id: str = Field(min_length=1, max_length=120)
    position: RelativePosition

    def to_domain(self) -> RelativeConstraint:
        return RelativeConstraint(
            reference_anchor_id=self.reference_anchor_id,
            position=self.position,
        )

    @classmethod
    def from_domain(cls, value: RelativeConstraint) -> Self:
        return cls(
            reference_anchor_id=value.reference_anchor_id,
            position=value.position,
        )


class ScreenAnchorDto(TutorialDto):
    anchor_id: str = Field(min_length=1, max_length=120)
    role: AnchorRole
    locator: SemanticLocatorDto
    relative_constraints: tuple[RelativeConstraintDto, ...] = Field(default=(), max_length=16)
    bounds_fallback: NormalizedBoundsDto | None = None

    def to_domain(self) -> ScreenAnchor:
        return ScreenAnchor(
            anchor_id=self.anchor_id,
            role=self.role,
            locator=self.locator.to_domain(),
            relative_constraints=tuple(
                constraint.to_domain() for constraint in self.relative_constraints
            ),
            bounds_fallback=(
                self.bounds_fallback.to_domain() if self.bounds_fallback is not None else None
            ),
        )

    @classmethod
    def from_domain(cls, value: ScreenAnchor) -> Self:
        return cls(
            anchor_id=value.anchor_id,
            role=value.role,
            locator=SemanticLocatorDto.from_domain(value.locator),
            relative_constraints=tuple(
                RelativeConstraintDto.from_domain(constraint)
                for constraint in value.relative_constraints
            ),
            bounds_fallback=(
                NormalizedBoundsDto.from_domain(value.bounds_fallback)
                if value.bounds_fallback is not None
                else None
            ),
        )


class TutorialNodeDto(TutorialDto):
    node_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=160)
    anchors: tuple[ScreenAnchorDto, ...] = Field(min_length=1, max_length=64)
    privacy_mode: PrivacyMode
    verification_status: VerificationStatus
    last_verified_version_code: int | None = Field(default=None, ge=1)

    def to_domain(self) -> TutorialNode:
        return TutorialNode(
            node_id=self.node_id,
            title=self.title,
            anchors=tuple(anchor.to_domain() for anchor in self.anchors),
            privacy_mode=self.privacy_mode,
            verification_status=self.verification_status,
            last_verified_version_code=self.last_verified_version_code,
        )

    @classmethod
    def from_domain(cls, value: TutorialNode) -> Self:
        return cls(
            node_id=value.node_id,
            title=value.title,
            anchors=tuple(ScreenAnchorDto.from_domain(anchor) for anchor in value.anchors),
            privacy_mode=value.privacy_mode,
            verification_status=value.verification_status,
            last_verified_version_code=value.last_verified_version_code,
        )


class TutorialTransitionDto(TutorialDto):
    transition_id: str = Field(min_length=1, max_length=120)
    source_node_id: str = Field(min_length=1, max_length=120)
    target_node_id: str = Field(min_length=1, max_length=120)
    action_kind: ActionKind
    instruction: str = Field(min_length=1, max_length=500)
    risk_level: RiskLevel
    target_anchor_id: str | None = Field(default=None, min_length=1, max_length=120)

    def to_domain(self) -> TutorialTransition:
        return TutorialTransition(
            transition_id=self.transition_id,
            source_node_id=self.source_node_id,
            target_node_id=self.target_node_id,
            action_kind=self.action_kind,
            instruction=self.instruction,
            risk_level=self.risk_level,
            target_anchor_id=self.target_anchor_id,
        )

    @classmethod
    def from_domain(cls, value: TutorialTransition) -> Self:
        return cls(
            transition_id=value.transition_id,
            source_node_id=value.source_node_id,
            target_node_id=value.target_node_id,
            action_kind=value.action_kind,
            instruction=value.instruction,
            risk_level=value.risk_level,
            target_anchor_id=value.target_anchor_id,
        )


class TutorialGraphDto(TutorialDto):
    """Public tutorial document; schema_version enables future evolution."""

    schema_version: Literal["1.0"] = "1.0"
    graph_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=160)
    recorded_app: AppIdentityDto
    start_node_id: str = Field(min_length=1)
    nodes: tuple[TutorialNodeDto, ...] = Field(min_length=1, max_length=128)
    transitions: tuple[TutorialTransitionDto, ...] = Field(max_length=256)

    def to_domain(self) -> TutorialGraph:
        return TutorialGraph(
            graph_id=self.graph_id,
            title=self.title,
            recorded_app=self.recorded_app.to_domain(),
            start_node_id=self.start_node_id,
            nodes=tuple(node.to_domain() for node in self.nodes),
            transitions=tuple(transition.to_domain() for transition in self.transitions),
        )

    @classmethod
    def from_domain(cls, value: TutorialGraph) -> Self:
        return cls(
            graph_id=value.graph_id,
            title=value.title,
            recorded_app=AppIdentityDto.from_domain(value.recorded_app),
            start_node_id=value.start_node_id,
            nodes=tuple(TutorialNodeDto.from_domain(node) for node in value.nodes),
            transitions=tuple(
                TutorialTransitionDto.from_domain(transition) for transition in value.transitions
            ),
        )
