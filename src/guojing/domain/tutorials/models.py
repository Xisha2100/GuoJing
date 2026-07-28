"""Value objects and entities used by recorded tutorial state graphs."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


@dataclass(frozen=True, slots=True)
class AppIdentity:
    """Stable Android application identity plus its installed version."""

    package_name: str
    version_name: str
    version_code: int

    def __post_init__(self) -> None:
        _require_non_blank(self.package_name, "package_name")
        _require_non_blank(self.version_name, "version_name")
        if self.version_code < 1:
            raise ValueError("version_code must be positive")


@dataclass(frozen=True, slots=True)
class NormalizedBounds:
    """Screen-relative rectangle whose coordinates stay between zero and one."""

    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        coordinates = (self.left, self.top, self.right, self.bottom)
        if any(
            not isfinite(coordinate) or coordinate < 0 or coordinate > 1
            for coordinate in coordinates
        ):
            raise ValueError("normalized bounds coordinates must be between 0 and 1")
        if self.left >= self.right:
            raise ValueError("left must be smaller than right")
        if self.top >= self.bottom:
            raise ValueError("top must be smaller than bottom")


@dataclass(frozen=True, slots=True)
class SemanticLocator:
    """Semantic ways to find a UI element before falling back to geometry."""

    resource_id: str | None = None
    content_description: str | None = None
    text: str | None = None
    ocr_text: str | None = None

    def __post_init__(self) -> None:
        values = (
            self.resource_id,
            self.content_description,
            self.text,
            self.ocr_text,
        )
        if not any(value is not None and value.strip() for value in values):
            raise ValueError("a semantic locator needs at least one non-blank value")
        for value in values:
            if value is not None and not value.strip():
                raise ValueError("semantic locator values must not be blank")


class AnchorRole(StrEnum):
    """How an anchor contributes to recognizing a screen."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    FORBIDDEN = "forbidden"


class RelativePosition(StrEnum):
    """Structural relation between two anchors."""

    LEFT_OF = "left_of"
    RIGHT_OF = "right_of"
    ABOVE = "above"
    BELOW = "below"
    INSIDE = "inside"
    NEAR = "near"


@dataclass(frozen=True, slots=True)
class RelativeConstraint:
    """Expected position of an anchor relative to another anchor."""

    reference_anchor_id: str
    position: RelativePosition

    def __post_init__(self) -> None:
        _require_non_blank(self.reference_anchor_id, "reference_anchor_id")


@dataclass(frozen=True, slots=True)
class ScreenAnchor:
    """A meaningful element used to recognize or operate on a screen."""

    anchor_id: str
    role: AnchorRole
    locator: SemanticLocator
    relative_constraints: tuple[RelativeConstraint, ...] = ()
    bounds_fallback: NormalizedBounds | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.anchor_id, "anchor_id")


class PrivacyMode(StrEnum):
    """How screen information may leave the Android device."""

    NETWORK_ALLOWED = "network_allowed"
    LOCAL_ONLY = "local_only"
    CAPTURE_PAUSED = "capture_paused"


class VerificationStatus(StrEnum):
    """Lifecycle state of a recorded tutorial node."""

    VERIFIED = "verified"
    PROVISIONAL = "provisional"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class TutorialNode:
    """A recognizable screen state in a recorded tutorial."""

    node_id: str
    title: str
    anchors: tuple[ScreenAnchor, ...]
    privacy_mode: PrivacyMode
    verification_status: VerificationStatus
    last_verified_version_code: int | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.node_id, "node_id")
        _require_non_blank(self.title, "title")
        if self.last_verified_version_code is not None and self.last_verified_version_code < 1:
            raise ValueError("last_verified_version_code must be positive")


class ActionKind(StrEnum):
    """User actions that may connect two tutorial states."""

    TAP = "tap"
    HOLD = "hold"
    SCROLL = "scroll"
    INPUT = "input"
    WAIT = "wait"
    SYSTEM_BACK = "system_back"


class RiskLevel(StrEnum):
    """Safety class of an action, independent from screen privacy."""

    LOW = "low"
    SENSITIVE = "sensitive"
    IRREVERSIBLE = "irreversible"
    FINANCIAL = "financial"


@dataclass(frozen=True, slots=True)
class TutorialTransition:
    """A user-performed action and the screen state expected afterwards."""

    transition_id: str
    source_node_id: str
    target_node_id: str
    action_kind: ActionKind
    instruction: str
    risk_level: RiskLevel
    target_anchor_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.transition_id, "transition_id")
        _require_non_blank(self.source_node_id, "source_node_id")
        _require_non_blank(self.target_node_id, "target_node_id")
        _require_non_blank(self.instruction, "instruction")
        if self.target_anchor_id is not None:
            _require_non_blank(self.target_anchor_id, "target_anchor_id")


@dataclass(frozen=True, slots=True)
class TutorialGraph:
    """A version-aware graph recorded for one Android application."""

    graph_id: str
    title: str
    recorded_app: AppIdentity
    start_node_id: str
    nodes: tuple[TutorialNode, ...]
    transitions: tuple[TutorialTransition, ...]

    def __post_init__(self) -> None:
        _require_non_blank(self.graph_id, "graph_id")
        _require_non_blank(self.title, "title")
        _require_non_blank(self.start_node_id, "start_node_id")
