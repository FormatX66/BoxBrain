"""Deterministic topic-boundary routing for the Aurum Chat Process Tree.

The router decides whether a new message stays on the current node, becomes a
child subproblem, or becomes a sibling topic. It intentionally accepts an
optional upstream relation hint but does not require a model call; simple,
auditable lexical evidence provides the fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from chat_process_tree import ChatProcessTree, ProcessNode


ROUTES = frozenset({"continue", "child_split", "sibling_split"})
RELATION_HINTS = frozenset({"same", "subproblem", "new", "unknown"})
_WORD = re.compile(r"[a-z0-9][a-z0-9_-]*")
_STOP = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do",
        "for", "from", "how", "i", "in", "is", "it", "of", "on", "or", "so",
        "that", "the", "this", "to", "we", "what", "when", "with", "you",
    }
)


@dataclass(frozen=True)
class TopicContext:
    node_id: str
    title: str
    objective: str
    concepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class TopicSignal:
    title: str
    objective: str
    concepts: tuple[str, ...] = ()
    relation_hint: str = "unknown"


@dataclass(frozen=True)
class RoutingDecision:
    route: str
    confidence: float
    reason_codes: tuple[str, ...]
    overlap: float

    def __post_init__(self) -> None:
        if self.route not in ROUTES:
            raise ValueError(f"unknown route: {self.route}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


def _tokens(*values: str, concepts: Iterable[str] = ()) -> frozenset[str]:
    parts: list[str] = []
    for value in values:
        parts.extend(_WORD.findall(value.lower()))
    for concept in concepts:
        parts.extend(_WORD.findall(str(concept).lower()))
    return frozenset(part for part in parts if len(part) > 1 and part not in _STOP)


def topic_overlap(current: TopicContext, incoming: TopicSignal) -> float:
    left = _tokens(current.title, current.objective, concepts=current.concepts)
    right = _tokens(incoming.title, incoming.objective, concepts=incoming.concepts)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def classify_topic_change(current: TopicContext, incoming: TopicSignal) -> RoutingDecision:
    hint = incoming.relation_hint.strip().lower()
    if hint not in RELATION_HINTS:
        raise ValueError(f"unknown relation hint: {incoming.relation_hint}")

    overlap = topic_overlap(current, incoming)
    shared_concepts = set(current.concepts) & set(incoming.concepts)

    if hint == "same":
        return RoutingDecision("continue", 0.98, ("explicit-same-topic",), overlap)
    if hint == "subproblem":
        return RoutingDecision("child_split", 0.98, ("explicit-subproblem",), overlap)
    if hint == "new":
        return RoutingDecision("sibling_split", 0.98, ("explicit-new-objective",), overlap)

    # High overlap means the user is still working the same objective. A medium
    # overlap or a shared durable concept is treated as a subproblem so the
    # sidebar/tree stays readable without severing useful lineage. Low overlap
    # is a material topic boundary and becomes a sibling lane.
    if overlap >= 0.42:
        return RoutingDecision("continue", min(0.95, 0.60 + overlap), ("high-topic-overlap",), overlap)
    if overlap >= 0.16 or shared_concepts:
        reasons = ["related-topic"]
        if shared_concepts:
            reasons.append("shared-durable-concept")
        return RoutingDecision("child_split", min(0.90, 0.56 + overlap), tuple(reasons), overlap)
    return RoutingDecision("sibling_split", min(0.92, 0.72 + (0.16 - overlap)), ("material-topic-boundary",), overlap)


def _next_sequence(tree: ChatProcessTree) -> int:
    return max(node.sequence for node in tree.nodes.values()) + 1


def route_into_tree(
    tree: ChatProcessTree,
    *,
    current_id: str,
    new_node_id: str,
    incoming: TopicSignal,
    summary: str = "",
    evidence_refs: Iterable[str] = (),
) -> tuple[ChatProcessTree, RoutingDecision, str]:
    """Classify a topic and materialize a split only when one is required.

    Returns ``(tree, decision, focus_node_id)``. A continue decision leaves the
    tree structurally unchanged and keeps focus on ``current_id``.
    """

    if current_id not in tree.nodes:
        raise ValueError(f"unknown current node: {current_id}")
    current = tree.nodes[current_id]
    context = TopicContext(
        node_id=current.node_id,
        title=current.title,
        objective=current.summary or current.title,
        concepts=current.concepts,
    )
    decision = classify_topic_change(context, incoming)
    if decision.route == "continue":
        return tree, decision, current_id

    if new_node_id in tree.nodes:
        raise ValueError(f"node already exists: {new_node_id}")

    if decision.route == "child_split":
        parent_id = current_id
    else:
        # Sibling splits stay beside the current objective. If the focused node
        # is the root, it becomes the parent because there is no higher sibling.
        parent_id = current.parent_id or tree.root_id

    lane_id = new_node_id
    node = ProcessNode(
        node_id=new_node_id,
        title=incoming.title.strip() or new_node_id,
        kind="process",
        state="active",
        lane_id=lane_id,
        sequence=_next_sequence(tree),
        parent_id=parent_id,
        summary=summary or incoming.objective,
        concepts=tuple(dict.fromkeys(incoming.concepts)),
        evidence_refs=tuple(dict.fromkeys(str(ref) for ref in evidence_refs if str(ref).strip())),
        state_history=("active",),
    )
    return tree.add(node), decision, new_node_id
