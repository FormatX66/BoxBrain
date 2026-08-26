"""Durable multi-lane chat/process tree for Future Branch.

Human conversation is usually presented as one focused path. Computer work does
not need to collapse to that path. This module keeps sibling process lanes,
concepts, evidence, dependencies, and merge provenance visible at the same time.

The tree is advisory state only. It cannot create execution authority, resolve a
physical boundary, or promote a candidate merely because branches were merged.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from typing import Iterable, Mapping


SCHEMA = "aurum-chat-process-tree-v1"
NODE_KINDS = frozenset({"conversation", "process", "concept", "decision", "checkpoint"})
NODE_STATES = frozenset(
    {"queued", "active", "running", "waiting", "blocked", "completed", "failed", "archived"}
)
ACTIVE_STATES = frozenset({"queued", "active", "running", "waiting", "blocked"})

_TRANSITIONS = {
    "queued": frozenset({"active", "waiting", "blocked", "archived"}),
    "active": frozenset({"running", "waiting", "blocked", "completed", "failed", "archived"}),
    "running": frozenset({"active", "waiting", "blocked", "completed", "failed"}),
    "waiting": frozenset({"active", "running", "blocked", "completed", "failed", "archived"}),
    "blocked": frozenset({"active", "waiting", "completed", "failed", "archived"}),
    "completed": frozenset({"archived"}),
    "failed": frozenset({"active", "archived"}),
    "archived": frozenset(),
}


class ChatProcessTreeError(ValueError):
    """Raised when a process tree would lose lineage or violate a safety invariant."""


def _strings(values: Iterable[str]) -> tuple[str, ...]:
    result = tuple(str(value).strip() for value in values)
    if any(not value for value in result):
        raise ChatProcessTreeError("tree identifiers and references must be non-empty")
    if len(set(result)) != len(result):
        raise ChatProcessTreeError("tree identifiers and references must be unique")
    return result


@dataclass(frozen=True)
class ProcessNode:
    node_id: str
    title: str
    kind: str
    state: str
    lane_id: str
    sequence: int
    parent_id: str | None = None
    summary: str = ""
    concepts: tuple[str, ...] = ()
    dependency_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    merged_from: tuple[str, ...] = ()
    boundary: str | None = None
    effect_allowed: bool = False
    authority_ref: str | None = None
    state_history: tuple[str, ...] = ()

    def validate_local(self) -> None:
        if not self.node_id.strip() or not self.title.strip() or not self.lane_id.strip():
            raise ChatProcessTreeError("node id, title, and lane id are required")
        if self.kind not in NODE_KINDS:
            raise ChatProcessTreeError(f"unknown node kind: {self.kind}")
        if self.state not in NODE_STATES:
            raise ChatProcessTreeError(f"unknown node state: {self.state}")
        if self.sequence < 0:
            raise ChatProcessTreeError("node sequence must be non-negative")
        for values in (self.concepts, self.dependency_ids, self.evidence_refs, self.merged_from):
            _strings(values)
        history = self.state_history or (self.state,)
        if any(value not in NODE_STATES for value in history) or history[-1] != self.state:
            raise ChatProcessTreeError("state history must end in the current valid state")
        if self.node_id in {self.parent_id, *self.dependency_ids, *self.merged_from}:
            raise ChatProcessTreeError("a node cannot reference itself")
        if self.effect_allowed and not self.authority_ref:
            raise ChatProcessTreeError("effect permission requires an external authority reference")
        if self.effect_allowed and self.boundary:
            raise ChatProcessTreeError("an unresolved boundary cannot be marked effect-allowed")

    def to_dict(self) -> dict:
        history = self.state_history or (self.state,)
        return {
            "node_id": self.node_id,
            "title": self.title,
            "kind": self.kind,
            "state": self.state,
            "lane_id": self.lane_id,
            "sequence": self.sequence,
            "parent_id": self.parent_id,
            "summary": self.summary,
            "concepts": list(self.concepts),
            "dependency_ids": list(self.dependency_ids),
            "evidence_refs": list(self.evidence_refs),
            "merged_from": list(self.merged_from),
            "boundary": self.boundary,
            "effect_allowed": self.effect_allowed,
            "authority_ref": self.authority_ref,
            "state_history": list(history),
        }

    @classmethod
    def from_dict(cls, raw: Mapping) -> "ProcessNode":
        state = str(raw["state"])
        return cls(
            node_id=str(raw["node_id"]),
            title=str(raw["title"]),
            kind=str(raw["kind"]),
            state=state,
            lane_id=str(raw["lane_id"]),
            sequence=int(raw["sequence"]),
            parent_id=None if raw.get("parent_id") is None else str(raw["parent_id"]),
            summary=str(raw.get("summary", "")),
            concepts=tuple(str(item) for item in raw.get("concepts", ())),
            dependency_ids=tuple(str(item) for item in raw.get("dependency_ids", ())),
            evidence_refs=tuple(str(item) for item in raw.get("evidence_refs", ())),
            merged_from=tuple(str(item) for item in raw.get("merged_from", ())),
            boundary=None if raw.get("boundary") is None else str(raw["boundary"]),
            effect_allowed=bool(raw.get("effect_allowed", False)),
            authority_ref=None if raw.get("authority_ref") is None else str(raw["authority_ref"]),
            state_history=tuple(str(item) for item in raw.get("state_history", (state,))),
        )


class ChatProcessTree:
    """Validated immutable snapshot of concurrent conversation/process lanes."""

    def __init__(
        self,
        *,
        thread_id: str,
        root_id: str,
        nodes: Iterable[ProcessNode],
        revision: int = 0,
    ) -> None:
        self.thread_id = str(thread_id).strip()
        self.root_id = str(root_id).strip()
        self.revision = int(revision)
        values = tuple(nodes)
        self.nodes = {node.node_id: node for node in values}
        if len(self.nodes) != len(values):
            raise ChatProcessTreeError("node ids must be unique")
        self.validate()

    def validate(self) -> None:
        if not self.thread_id or not self.root_id:
            raise ChatProcessTreeError("thread id and root id are required")
        if self.revision < 0:
            raise ChatProcessTreeError("revision must be non-negative")
        if self.root_id not in self.nodes:
            raise ChatProcessTreeError("root node is missing")
        root = self.nodes[self.root_id]
        if root.parent_id is not None:
            raise ChatProcessTreeError("root node cannot have a parent")

        for node in self.nodes.values():
            node.validate_local()
            if node.node_id != self.root_id and node.parent_id not in self.nodes:
                raise ChatProcessTreeError(f"missing parent for {node.node_id}")
            refs = (*node.dependency_ids, *node.merged_from)
            missing = [ref for ref in refs if ref not in self.nodes]
            if missing:
                raise ChatProcessTreeError(f"missing referenced nodes for {node.node_id}: {missing}")
            ordered_refs = ([node.parent_id] if node.parent_id else []) + list(refs)
            if any(self.nodes[ref].sequence >= node.sequence for ref in ordered_refs):
                raise ChatProcessTreeError("parents, dependencies, and merge sources must precede a node")
            if node.merged_from and len(node.merged_from) < 2:
                raise ChatProcessTreeError("a merge must preserve at least two source nodes")

    def _copy(self, nodes: Iterable[ProcessNode]) -> "ChatProcessTree":
        return ChatProcessTree(
            thread_id=self.thread_id,
            root_id=self.root_id,
            nodes=nodes,
            revision=self.revision + 1,
        )

    def add(self, node: ProcessNode) -> "ChatProcessTree":
        if node.node_id in self.nodes:
            raise ChatProcessTreeError(f"node already exists: {node.node_id}")
        return self._copy((*self.nodes.values(), node))

    def transition(self, node_id: str, state: str, *, evidence_ref: str | None = None) -> "ChatProcessTree":
        if node_id not in self.nodes:
            raise ChatProcessTreeError(f"unknown node: {node_id}")
        current = self.nodes[node_id]
        if state not in _TRANSITIONS[current.state]:
            raise ChatProcessTreeError(f"invalid transition: {current.state} -> {state}")
        evidence = current.evidence_refs
        if evidence_ref:
            evidence = (*evidence, str(evidence_ref))
        changed = replace(
            current,
            state=state,
            evidence_refs=tuple(dict.fromkeys(evidence)),
            state_history=(*(current.state_history or (current.state,)), state),
        )
        return self._copy(changed if node.node_id == node_id else node for node in self.nodes.values())

    def focus_path(self, node_id: str) -> tuple[ProcessNode, ...]:
        if node_id not in self.nodes:
            raise ChatProcessTreeError(f"unknown focus node: {node_id}")
        path: list[ProcessNode] = []
        cursor: ProcessNode | None = self.nodes[node_id]
        while cursor is not None:
            path.append(cursor)
            cursor = self.nodes[cursor.parent_id] if cursor.parent_id else None
        return tuple(reversed(path))

    def active_frontier(self) -> tuple[ProcessNode, ...]:
        return tuple(
            sorted(
                (node for node in self.nodes.values() if node.state in ACTIVE_STATES),
                key=lambda node: (node.sequence, node.lane_id, node.node_id),
            )
        )

    def concept_index(self) -> dict[str, tuple[str, ...]]:
        index: dict[str, list[str]] = {}
        for node in sorted(self.nodes.values(), key=lambda item: (item.sequence, item.node_id)):
            for concept in node.concepts:
                index.setdefault(concept, []).append(node.node_id)
        return {concept: tuple(node_ids) for concept, node_ids in sorted(index.items())}

    def _common_parent(self, node_ids: tuple[str, ...]) -> str:
        paths = [self.focus_path(node_id) for node_id in node_ids]
        shared = set(node.node_id for node in paths[0])
        for path in paths[1:]:
            shared.intersection_update(node.node_id for node in path)
        return max(shared, key=lambda node_id: self.nodes[node_id].sequence)

    def merge_lanes(
        self,
        node_ids: Iterable[str],
        *,
        node_id: str,
        title: str,
        lane_id: str,
        summary: str = "",
        concepts: Iterable[str] = (),
    ) -> "ChatProcessTree":
        sources = _strings(node_ids)
        if len(sources) < 2:
            raise ChatProcessTreeError("at least two lanes are required for a merge")
        if any(source not in self.nodes for source in sources):
            raise ChatProcessTreeError("all merge sources must exist")
        source_nodes = tuple(self.nodes[source] for source in sources)
        merged_concepts = tuple(
            dict.fromkeys((*concepts, *(concept for source in source_nodes for concept in source.concepts)))
        )
        boundaries = tuple(dict.fromkeys(source.boundary for source in source_nodes if source.boundary))
        boundary = boundaries[0] if len(boundaries) == 1 else "mixed" if boundaries else None
        merged = ProcessNode(
            node_id=node_id,
            title=title,
            kind="checkpoint",
            state="active",
            lane_id=lane_id,
            sequence=max(source.sequence for source in source_nodes) + 1,
            parent_id=self._common_parent(sources),
            summary=summary,
            concepts=merged_concepts,
            evidence_refs=tuple(
                dict.fromkeys(ref for source in source_nodes for ref in source.evidence_refs)
            ),
            merged_from=sources,
            boundary=boundary,
            effect_allowed=False,
            authority_ref=None,
            state_history=("active",),
        )
        return self.add(merged)

    def to_dict(self, *, focus_id: str | None = None) -> dict:
        focus = focus_id or self.root_id
        return {
            "schema": SCHEMA,
            "thread_id": self.thread_id,
            "root_id": self.root_id,
            "revision": self.revision,
            "focus_path": [node.node_id for node in self.focus_path(focus)],
            "active_frontier": [node.node_id for node in self.active_frontier()],
            "concept_index": {key: list(value) for key, value in self.concept_index().items()},
            "nodes": [
                node.to_dict()
                for node in sorted(self.nodes.values(), key=lambda item: (item.sequence, item.node_id))
            ],
            "invariants": {
                "human_focus_collapses_machine_lanes": False,
                "completed_or_archived_nodes_are_deleted": False,
                "merge_preserves_source_provenance": True,
                "tree_grants_execution_authority": False,
                "tree_resolves_physical_boundaries": False,
            },
        }

    def to_json(self, *, focus_id: str | None = None) -> str:
        return json.dumps(self.to_dict(focus_id=focus_id), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, raw: Mapping) -> "ChatProcessTree":
        if raw.get("schema") != SCHEMA:
            raise ChatProcessTreeError("unexpected chat process tree schema")
        return cls(
            thread_id=str(raw["thread_id"]),
            root_id=str(raw["root_id"]),
            revision=int(raw.get("revision", 0)),
            nodes=(ProcessNode.from_dict(node) for node in raw.get("nodes", ())),
        )

    @classmethod
    def from_json(cls, text: str) -> "ChatProcessTree":
        raw = json.loads(text)
        if not isinstance(raw, dict):
            raise ChatProcessTreeError("chat process tree JSON must contain an object")
        return cls.from_dict(raw)
