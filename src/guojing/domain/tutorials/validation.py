"""Structural validation for tutorial graphs created by recording tools."""

from collections import Counter, deque
from dataclasses import dataclass
from enum import StrEnum

from guojing.domain.tutorials.models import (
    ActionKind,
    AnchorRole,
    TutorialGraph,
    TutorialNode,
    TutorialTransition,
    VerificationStatus,
)


class GraphIssueCode(StrEnum):
    """Machine-readable reasons why a tutorial graph is invalid."""

    DUPLICATE_NODE_ID = "duplicate_node_id"
    DUPLICATE_TRANSITION_ID = "duplicate_transition_id"
    MISSING_START_NODE = "missing_start_node"
    DUPLICATE_ANCHOR_ID = "duplicate_anchor_id"
    NO_REQUIRED_ANCHOR = "no_required_anchor"
    UNKNOWN_RELATIVE_ANCHOR = "unknown_relative_anchor"
    SELF_RELATIVE_ANCHOR = "self_relative_anchor"
    VERIFIED_WITHOUT_VERSION = "verified_without_version"
    UNKNOWN_SOURCE_NODE = "unknown_source_node"
    UNKNOWN_TARGET_NODE = "unknown_target_node"
    MISSING_TARGET_ANCHOR = "missing_target_anchor"
    UNEXPECTED_TARGET_ANCHOR = "unexpected_target_anchor"
    UNKNOWN_TARGET_ANCHOR = "unknown_target_anchor"
    FORBIDDEN_TARGET_ANCHOR = "forbidden_target_anchor"
    UNREACHABLE_NODE = "unreachable_node"
    NO_TERMINAL_NODE = "no_terminal_node"


@dataclass(frozen=True, slots=True)
class GraphValidationIssue:
    """One actionable graph validation problem."""

    code: GraphIssueCode
    message: str
    node_id: str | None = None
    transition_id: str | None = None


class InvalidTutorialGraph(ValueError):
    """Raised when a graph must be valid before entering an application use case."""

    def __init__(self, issues: tuple[GraphValidationIssue, ...]) -> None:
        self.issues = issues
        details = "; ".join(issue.message for issue in issues)
        super().__init__(details)


_TARGET_REQUIRED_ACTIONS = frozenset({ActionKind.TAP, ActionKind.HOLD, ActionKind.INPUT})
_TARGET_FORBIDDEN_ACTIONS = frozenset({ActionKind.WAIT, ActionKind.SYSTEM_BACK})


def validate_tutorial_graph(graph: TutorialGraph) -> tuple[GraphValidationIssue, ...]:
    """Return every structural issue so an admin can repair a draft in one pass."""
    issues: list[GraphValidationIssue] = []
    node_counts = Counter(node.node_id for node in graph.nodes)
    transition_counts = Counter(transition.transition_id for transition in graph.transitions)
    node_by_id = {node.node_id: node for node in graph.nodes}

    for node_id, count in node_counts.items():
        if count > 1:
            issues.append(
                GraphValidationIssue(
                    GraphIssueCode.DUPLICATE_NODE_ID,
                    f"node id {node_id!r} appears {count} times",
                    node_id=node_id,
                )
            )

    for transition_id, count in transition_counts.items():
        if count > 1:
            issues.append(
                GraphValidationIssue(
                    GraphIssueCode.DUPLICATE_TRANSITION_ID,
                    f"transition id {transition_id!r} appears {count} times",
                    transition_id=transition_id,
                )
            )

    if graph.start_node_id not in node_by_id:
        issues.append(
            GraphValidationIssue(
                GraphIssueCode.MISSING_START_NODE,
                f"start node {graph.start_node_id!r} does not exist",
                node_id=graph.start_node_id,
            )
        )

    for node in graph.nodes:
        issues.extend(_validate_node(node))

    valid_edges: dict[str, set[str]] = {node_id: set() for node_id in node_by_id}
    for transition in graph.transitions:
        source = node_by_id.get(transition.source_node_id)
        if source is None:
            issues.append(
                GraphValidationIssue(
                    GraphIssueCode.UNKNOWN_SOURCE_NODE,
                    f"transition {transition.transition_id!r} has an unknown source node",
                    transition_id=transition.transition_id,
                    node_id=transition.source_node_id,
                )
            )
        if transition.target_node_id not in node_by_id:
            issues.append(
                GraphValidationIssue(
                    GraphIssueCode.UNKNOWN_TARGET_NODE,
                    f"transition {transition.transition_id!r} has an unknown target node",
                    transition_id=transition.transition_id,
                    node_id=transition.target_node_id,
                )
            )
        if source is not None:
            issues.extend(_validate_transition_target(source, transition))
        if source is not None and transition.target_node_id in node_by_id:
            valid_edges[source.node_id].add(transition.target_node_id)

    if graph.start_node_id in node_by_id:
        reachable = _reachable_nodes(graph.start_node_id, valid_edges)
        for node_id in node_by_id.keys() - reachable:
            issues.append(
                GraphValidationIssue(
                    GraphIssueCode.UNREACHABLE_NODE,
                    f"node {node_id!r} cannot be reached from the start node",
                    node_id=node_id,
                )
            )

    if node_by_id and all(valid_edges[node_id] for node_id in node_by_id):
        issues.append(
            GraphValidationIssue(
                GraphIssueCode.NO_TERMINAL_NODE,
                "the tutorial graph needs at least one terminal node",
            )
        )

    return tuple(issues)


def require_valid_tutorial_graph(graph: TutorialGraph) -> None:
    """Raise one exception containing all structural graph issues."""
    issues = validate_tutorial_graph(graph)
    if issues:
        raise InvalidTutorialGraph(issues)


def _validate_node(node: TutorialNode) -> list[GraphValidationIssue]:
    issues: list[GraphValidationIssue] = []
    anchor_counts = Counter(anchor.anchor_id for anchor in node.anchors)
    anchor_ids = set(anchor_counts)

    for anchor_id, count in anchor_counts.items():
        if count > 1:
            issues.append(
                GraphValidationIssue(
                    GraphIssueCode.DUPLICATE_ANCHOR_ID,
                    f"anchor id {anchor_id!r} appears {count} times in node {node.node_id!r}",
                    node_id=node.node_id,
                )
            )

    if not any(anchor.role is AnchorRole.REQUIRED for anchor in node.anchors):
        issues.append(
            GraphValidationIssue(
                GraphIssueCode.NO_REQUIRED_ANCHOR,
                f"node {node.node_id!r} needs at least one required anchor",
                node_id=node.node_id,
            )
        )

    for anchor in node.anchors:
        for constraint in anchor.relative_constraints:
            if constraint.reference_anchor_id == anchor.anchor_id:
                issues.append(
                    GraphValidationIssue(
                        GraphIssueCode.SELF_RELATIVE_ANCHOR,
                        f"anchor {anchor.anchor_id!r} cannot be relative to itself",
                        node_id=node.node_id,
                    )
                )
            elif constraint.reference_anchor_id not in anchor_ids:
                issues.append(
                    GraphValidationIssue(
                        GraphIssueCode.UNKNOWN_RELATIVE_ANCHOR,
                        (
                            f"anchor {anchor.anchor_id!r} references unknown anchor "
                            f"{constraint.reference_anchor_id!r}"
                        ),
                        node_id=node.node_id,
                    )
                )

    if (
        node.verification_status is VerificationStatus.VERIFIED
        and node.last_verified_version_code is None
    ):
        issues.append(
            GraphValidationIssue(
                GraphIssueCode.VERIFIED_WITHOUT_VERSION,
                f"verified node {node.node_id!r} needs a last verified version code",
                node_id=node.node_id,
            )
        )

    return issues


def _validate_transition_target(
    source: TutorialNode,
    transition: TutorialTransition,
) -> list[GraphValidationIssue]:
    issues: list[GraphValidationIssue] = []
    if transition.action_kind in _TARGET_REQUIRED_ACTIONS and transition.target_anchor_id is None:
        issues.append(
            GraphValidationIssue(
                GraphIssueCode.MISSING_TARGET_ANCHOR,
                f"action {transition.action_kind.value!r} needs a target anchor",
                transition_id=transition.transition_id,
                node_id=source.node_id,
            )
        )
        return issues

    if transition.action_kind in _TARGET_FORBIDDEN_ACTIONS:
        if transition.target_anchor_id is not None:
            issues.append(
                GraphValidationIssue(
                    GraphIssueCode.UNEXPECTED_TARGET_ANCHOR,
                    f"action {transition.action_kind.value!r} must not target an anchor",
                    transition_id=transition.transition_id,
                    node_id=source.node_id,
                )
            )
        return issues

    if transition.target_anchor_id is None:
        return issues

    anchor_by_id = {anchor.anchor_id: anchor for anchor in source.anchors}
    target_anchor = anchor_by_id.get(transition.target_anchor_id)
    if target_anchor is None:
        issues.append(
            GraphValidationIssue(
                GraphIssueCode.UNKNOWN_TARGET_ANCHOR,
                (
                    f"transition {transition.transition_id!r} targets unknown anchor "
                    f"{transition.target_anchor_id!r}"
                ),
                transition_id=transition.transition_id,
                node_id=source.node_id,
            )
        )
    elif target_anchor.role is AnchorRole.FORBIDDEN:
        issues.append(
            GraphValidationIssue(
                GraphIssueCode.FORBIDDEN_TARGET_ANCHOR,
                f"transition {transition.transition_id!r} targets a forbidden anchor",
                transition_id=transition.transition_id,
                node_id=source.node_id,
            )
        )
    return issues


def _reachable_nodes(start_node_id: str, edges: dict[str, set[str]]) -> set[str]:
    reachable: set[str] = set()
    remaining = deque([start_node_id])
    while remaining:
        node_id = remaining.popleft()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        remaining.extend(edges.get(node_id, ()))
    return reachable
