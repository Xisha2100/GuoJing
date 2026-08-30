"""Privacy-bound value objects for screenshot help requests."""

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

MAX_SCREENSHOT_DIMENSION = 1_440
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
MAX_QUESTION_LENGTH = 300
MAX_REDACTIONS = 20
MAX_WORKFLOW_STAGE_LENGTH = 40
MAX_TUTORIAL_MATCH_REASON_LENGTH = 80
MAX_TUTORIAL_ID_LENGTH = 120


class HelpRequestIntent(StrEnum):
    """The deterministic route requested after the screenshot is received."""

    RECORDED_TUTORIAL = "recorded_tutorial"
    GENERAL_GUIDANCE = "general_guidance"


class HelpRequestProcessingRoute(StrEnum):
    """The next processing branch, without claiming that a model ran."""

    TUTORIAL_MATCH = "tutorial_match"
    GENERAL_GUIDANCE = "general_guidance"


class HelpRequestProcessingStatus(StrEnum):
    """Observable lifecycle states for a submitted help request."""

    RECEIVED = "received"
    PROCESSING = "processing"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    GUIDANCE_READY = "guidance_ready"


@dataclass(frozen=True, slots=True)
class HelpRequestTutorialMatch:
    """Safe tutorial selection metadata retained for polling and review."""

    status: str
    reason: str
    graph_id: str | None = None
    node_id: str | None = None
    revision_number: int | None = None

    def __post_init__(self) -> None:
        if not self.status.strip() or len(self.status) > MAX_WORKFLOW_STAGE_LENGTH:
            raise ValueError("tutorial match status must contain 1 to 40 characters")
        if not self.reason.strip() or len(self.reason) > MAX_TUTORIAL_MATCH_REASON_LENGTH:
            raise ValueError("tutorial match reason must contain 1 to 80 characters")
        for value, field_name in (
            (self.graph_id, "tutorial graph_id"),
            (self.node_id, "tutorial node_id"),
        ):
            if value is not None and (not value.strip() or len(value) > MAX_TUTORIAL_ID_LENGTH):
                raise ValueError(f"{field_name} must contain 1 to 120 characters")
        if self.revision_number is not None and self.revision_number < 1:
            raise ValueError("tutorial revision_number must be positive")
        if self.status == "matched" and (
            self.graph_id is None or self.node_id is None or self.revision_number is None
        ):
            raise ValueError("matched tutorial metadata must include a candidate")


_UNSAFE_GUIDANCE_TERMS = (
    "转账",
    "汇款",
    "收款",
    "提现",
    "充值",
    "付款",
    "支付",
    "支付密码",
    "发送金额",
    "发红包",
    "删除账号",
    "删除账户",
    "确认删除",
    "注销账号",
    "注销账户",
    "输入密码",
    "输入支付密码",
    "填写密码",
    "填写支付密码",
    "键入密码",
    "键入支付密码",
    "输入验证码",
    "填写验证码",
    "确认购买",
    "立即下单",
    "确认下单",
    "购买",
)


def find_unsafe_guidance_terms(value: str) -> tuple[str, ...]:
    """Return dangerous operations that must never become automatic guidance."""
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKC", value).casefold()
        if character.isalnum()
    )
    return tuple(term for term in _UNSAFE_GUIDANCE_TERMS if term in normalized)


@dataclass(frozen=True, slots=True)
class HelpRequestGuidanceStep:
    """A manual, reviewable instruction returned by a future processor.

    The contract intentionally has no node action, gesture, coordinate or
    payment command. A client may explain this step, but the user must still
    operate the target application and the execution engine must verify the
    resulting page before advancing.
    """

    step_id: str
    title: str
    instruction: str
    requires_manual_action: bool = True

    def __post_init__(self) -> None:
        if not self.step_id.strip() or len(self.step_id) > 64:
            raise ValueError("guidance step_id must contain 1 to 64 characters")
        if not self.title.strip() or len(self.title) > 120:
            raise ValueError("guidance title must contain 1 to 120 characters")
        if not self.instruction.strip() or len(self.instruction) > 500:
            raise ValueError("guidance instruction must contain 1 to 500 characters")
        if not self.requires_manual_action:
            raise ValueError("guidance steps must require manual user action")
        unsafe_terms = find_unsafe_guidance_terms(f"{self.title}\n{self.instruction}")
        if unsafe_terms:
            joined = ", ".join(unsafe_terms)
            raise ValueError(f"guidance contains blocked irreversible operations: {joined}")


@dataclass(frozen=True, slots=True)
class HelpRequestGuidance:
    """A bounded list of explanatory steps, never an executable plan."""

    title: str
    steps: tuple[HelpRequestGuidanceStep, ...]

    def __post_init__(self) -> None:
        if not self.title.strip() or len(self.title) > 160:
            raise ValueError("guidance title must contain 1 to 160 characters")
        unsafe_terms = find_unsafe_guidance_terms(self.title)
        if unsafe_terms:
            joined = ", ".join(unsafe_terms)
            raise ValueError(f"guidance contains blocked irreversible operations: {joined}")
        if not 1 <= len(self.steps) <= 20:
            raise ValueError("guidance must contain 1 to 20 steps")


@dataclass(frozen=True, slots=True)
class HelpRequestResult:
    """Status metadata retained after the sanitized image is discarded."""

    request_id: UUID
    client_request_id: UUID
    intent: HelpRequestIntent
    processing_route: HelpRequestProcessingRoute
    processing_status: HelpRequestProcessingStatus
    received_at: datetime
    updated_at: datetime
    guidance: HelpRequestGuidance | None = None
    human_review_reason: str | None = None
    workflow_stage: str | None = None
    tutorial_match: HelpRequestTutorialMatch | None = None

    def __post_init__(self) -> None:
        if self.updated_at < self.received_at:
            raise ValueError("updated_at cannot be earlier than received_at")
        if self.workflow_stage is not None and (
            not self.workflow_stage.strip() or len(self.workflow_stage) > MAX_WORKFLOW_STAGE_LENGTH
        ):
            raise ValueError("workflow_stage must contain 1 to 40 characters")
        if self.processing_status is HelpRequestProcessingStatus.GUIDANCE_READY:
            if self.guidance is None:
                raise ValueError("guidance_ready results must include guidance")
            if self.human_review_reason is not None:
                raise ValueError("guidance_ready results cannot include a review reason")
        elif self.guidance is not None:
            raise ValueError("guidance is only available when guidance is ready")
        if self.processing_status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW:
            if not self.human_review_reason or not self.human_review_reason.strip():
                raise ValueError("human review results need a non-empty reason")
        elif self.human_review_reason is not None:
            raise ValueError("a review reason is only available during human review")

    def transition(
        self,
        status: HelpRequestProcessingStatus,
        updated_at: datetime,
        *,
        guidance: HelpRequestGuidance | None = None,
        human_review_reason: str | None = None,
        workflow_stage: str | None = None,
        tutorial_match: HelpRequestTutorialMatch | None = None,
    ) -> "HelpRequestResult":
        """Apply one allowed forward-only transition."""
        if updated_at < self.updated_at:
            raise ValueError("updated_at cannot move backwards")
        allowed = {
            HelpRequestProcessingStatus.RECEIVED: {
                HelpRequestProcessingStatus.PROCESSING,
            },
            HelpRequestProcessingStatus.PROCESSING: {
                HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW,
                HelpRequestProcessingStatus.GUIDANCE_READY,
            },
            HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW: {
                HelpRequestProcessingStatus.GUIDANCE_READY,
            },
            HelpRequestProcessingStatus.GUIDANCE_READY: set(),
        }
        if status not in allowed[self.processing_status]:
            raise ValueError(
                f"cannot transition from {self.processing_status} to {status}",
            )
        return HelpRequestResult(
            request_id=self.request_id,
            client_request_id=self.client_request_id,
            intent=self.intent,
            processing_route=self.processing_route,
            processing_status=status,
            received_at=self.received_at,
            updated_at=updated_at,
            guidance=guidance,
            human_review_reason=human_review_reason,
            workflow_stage=self.workflow_stage if workflow_stage is None else workflow_stage,
            tutorial_match=self.tutorial_match if tutorial_match is None else tutorial_match,
        )

    def matches_request(self, request_id: UUID, client_request_id: UUID) -> bool:
        """Check both server and client identifiers before applying a response."""
        return self.request_id == request_id and self.client_request_id == client_request_id


@dataclass(frozen=True, slots=True)
class HelpRequestCommand:
    """Metadata accepted after the client has locally sanitized an image."""

    client_request_id: UUID
    intent: HelpRequestIntent
    question: str
    image_media_type: str
    image_width: int
    image_height: int
    redaction_count: int
    no_sensitive_content_confirmed: bool
    sanitized_sha256: str
    send_consent: bool

    def __post_init__(self) -> None:
        if not self.question.strip() or len(self.question) > MAX_QUESTION_LENGTH:
            raise ValueError("question must contain 1 to 300 characters")
        if self.image_media_type != "image/jpeg":
            raise ValueError("only sanitized image/jpeg screenshots are accepted")
        if not 1 <= self.image_width <= MAX_SCREENSHOT_DIMENSION:
            raise ValueError("image_width is outside the allowed range")
        if not 1 <= self.image_height <= MAX_SCREENSHOT_DIMENSION:
            raise ValueError("image_height is outside the allowed range")
        if not 0 <= self.redaction_count <= MAX_REDACTIONS:
            raise ValueError("redaction_count is outside the allowed range")
        if self.redaction_count == 0 and not self.no_sensitive_content_confirmed:
            raise ValueError("a zero-mask request needs an explicit privacy confirmation")
        if self.redaction_count > 0 and self.no_sensitive_content_confirmed:
            raise ValueError("redactions and no-sensitive confirmation are mutually exclusive")
        if len(self.sanitized_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sanitized_sha256
        ):
            raise ValueError("sanitized_sha256 must be a lowercase SHA-256 digest")
        if not self.send_consent:
            raise ValueError("explicit send consent is required")


def verify_sanitized_image(image: bytes | bytearray, expected_sha256: str) -> None:
    """Verify size and digest without retaining the image in a domain object."""
    if not 1 <= len(image) <= MAX_SCREENSHOT_BYTES:
        raise ValueError("sanitized image size is outside the allowed range")
    if len(image) < 4 or image[:2] != b"\xff\xd8" or image[-2:] != b"\xff\xd9":
        raise ValueError("sanitized image is not a JPEG byte stream")
    actual_sha256 = sha256(image).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("sanitized image digest does not match the request metadata")
