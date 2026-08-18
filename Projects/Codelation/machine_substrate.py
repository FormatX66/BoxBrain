from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA = "aurum-machine-substrate-v1"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ObjectStore:
    """Small machine-native content-addressed store.

    Git remains a bootstrap transport for the project, but Aurum's internal state does not
    need Git semantics. Objects are immutable and addressed by SHA-256; refs are the only
    mutable names. This is enough for blobs, trees, commits, execution evidence, and later
    replication across any carrier.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.refs = self.root / "refs"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.refs.mkdir(parents=True, exist_ok=True)

    def _object_path(self, object_id: str) -> Path:
        if len(object_id) != 64 or any(c not in "0123456789abcdef" for c in object_id):
            raise ValueError("invalid object id")
        return self.objects / object_id[:2] / object_id[2:]

    def put_bytes(self, data: bytes) -> str:
        object_id = _sha256(data)
        path = self._object_path(object_id)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
        return object_id

    def get_bytes(self, object_id: str) -> bytes:
        path = self._object_path(object_id)
        data = path.read_bytes()
        if _sha256(data) != object_id:
            raise ValueError(f"object integrity failure: {object_id}")
        return data

    def put_object(self, kind: str, payload: Mapping[str, Any] | Sequence[Any]) -> str:
        envelope = {"kind": kind, "payload": payload, "schema": SCHEMA}
        return self.put_bytes(_canonical_json(envelope))

    def get_object(self, object_id: str) -> dict[str, Any]:
        value = json.loads(self.get_bytes(object_id).decode("utf-8"))
        if value.get("schema") != SCHEMA:
            raise ValueError("unsupported object schema")
        return value

    def snapshot(self, files: Mapping[str, bytes]) -> str:
        entries: dict[str, str] = {}
        for name in sorted(files):
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"unsafe snapshot path: {name}")
            entries[name] = self.put_bytes(files[name])
        return self.put_object("tree", entries)

    def commit(
        self,
        tree: str,
        *,
        parents: Sequence[str] = (),
        message: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        # Reading proves referenced objects exist and are intact before the commit is made.
        tree_obj = self.get_object(tree)
        if tree_obj.get("kind") != "tree":
            raise ValueError("commit tree must reference a tree object")
        for parent in parents:
            parent_obj = self.get_object(parent)
            if parent_obj.get("kind") != "commit":
                raise ValueError("parent must reference a commit object")
        payload = {
            "tree": tree,
            "parents": list(parents),
            "message": message,
            "metadata": dict(metadata or {}),
        }
        return self.put_object("commit", payload)

    def update_ref(self, name: str, object_id: str) -> None:
        if not name or name.startswith("/") or ".." in Path(name).parts:
            raise ValueError("unsafe ref name")
        self.get_bytes(object_id)
        path = self.refs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(object_id + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def read_ref(self, name: str) -> str | None:
        path = self.refs / name
        if not path.exists():
            return None
        value = path.read_text(encoding="utf-8").strip()
        self.get_bytes(value)
        return value


@dataclass(frozen=True)
class Capsule:
    """Runtime-neutral execution contract.

    The capsule describes capability, inputs and deterministic intent. Python, shell,
    containers, WebAssembly, a future Aurum VM, or native machine code can all become
    executors without changing the scheduler's representation.
    """

    name: str
    runtime: str
    entrypoint: tuple[str, ...]
    requires: frozenset[str] = frozenset()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    dependencies: tuple[str, ...] = ()
    posture: str = "safe"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "runtime": self.runtime,
            "entrypoint": list(self.entrypoint),
            "requires": sorted(self.requires),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "environment": dict(self.environment),
            "dependencies": list(self.dependencies),
            "posture": self.posture,
        }

    @property
    def identity(self) -> str:
        return _sha256(_canonical_json(self.as_dict()))


@dataclass(frozen=True)
class ComputeNode:
    name: str
    capabilities: frozenset[str]
    slots: int = 1
    ephemeral: bool = True
    authority: str = "test-world"


@dataclass(frozen=True)
class Assignment:
    capsule: str
    capsule_id: str
    node: str
    posture: str


@dataclass
class FarmPlan:
    assignments: list[Assignment] = field(default_factory=list)
    blocked: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.blocked

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "aurum-machine-farm-plan-v1",
            "complete": self.complete,
            "assignments": [assignment.__dict__ for assignment in self.assignments],
            "blocked": {name: list(missing) for name, missing in sorted(self.blocked.items())},
        }


class ProcessorFarm:
    """Capability scheduler over whatever compute Aurum currently possesses."""

    def __init__(self, nodes: Iterable[ComputeNode]) -> None:
        self.nodes = tuple(nodes)
        if not self.nodes:
            raise ValueError("processor farm requires at least one node")

    def plan(self, capsules: Sequence[Capsule]) -> FarmPlan:
        names = [capsule.name for capsule in capsules]
        if len(set(names)) != len(names):
            raise ValueError("capsule names must be unique")
        known = set(names)
        for capsule in capsules:
            unknown = set(capsule.dependencies) - known
            if unknown:
                raise ValueError(f"{capsule.name} depends on unknown capsules: {sorted(unknown)}")

        remaining_slots = {node.name: node.slots for node in self.nodes}
        assignments: list[Assignment] = []
        blocked: dict[str, tuple[str, ...]] = {}

        # Harder-to-place tasks are scheduled first; this avoids consuming a specialized
        # node with a generic task while a later capsule has no compatible alternative.
        ordered = sorted(capsules, key=lambda c: (-len(c.requires), c.name))
        for capsule in ordered:
            candidates = [
                node
                for node in self.nodes
                if remaining_slots[node.name] > 0 and capsule.requires <= node.capabilities
            ]
            if not candidates:
                union = frozenset().union(*(node.capabilities for node in self.nodes))
                missing = tuple(sorted(capsule.requires - union))
                blocked[capsule.name] = missing or ("capacity",)
                continue
            candidates.sort(
                key=lambda node: (
                    len(node.capabilities - capsule.requires),
                    -remaining_slots[node.name],
                    node.name,
                )
            )
            node = candidates[0]
            remaining_slots[node.name] -= 1
            assignments.append(
                Assignment(
                    capsule=capsule.name,
                    capsule_id=capsule.identity,
                    node=node.name,
                    posture=capsule.posture,
                )
            )
        assignments.sort(key=lambda assignment: assignment.capsule)
        return FarmPlan(assignments=assignments, blocked=blocked)


class EvidenceLedger:
    def __init__(self, store: ObjectStore) -> None:
        self.store = store

    def record_result(
        self,
        *,
        capsule: Capsule,
        node: ComputeNode,
        status: str,
        observations: Mapping[str, Any],
        artifacts: Mapping[str, bytes] | None = None,
        parent: str | None = None,
    ) -> str:
        artifact_ids = {
            name: self.store.put_bytes(data)
            for name, data in sorted((artifacts or {}).items())
        }
        result_id = self.store.put_object(
            "execution-result",
            {
                "capsule": capsule.as_dict(),
                "capsule_id": capsule.identity,
                "node": node.name,
                "status": status,
                "observations": dict(observations),
                "artifacts": artifact_ids,
            },
        )
        tree = self.store.snapshot({"result": result_id.encode("ascii")})
        commit = self.store.commit(
            tree,
            parents=(parent,) if parent else (),
            message=f"{capsule.name}: {status}",
            metadata={"node": node.name, "capsule_id": capsule.identity},
        )
        self.store.update_ref(f"results/{capsule.name}", commit)
        return commit


def default_farm() -> ProcessorFarm:
    # This is a logical machine. Carriers can change without changing the work model.
    return ProcessorFarm(
        (
            ComputeNode(
                "github-x64-a",
                frozenset({"build", "git", "network", "python", "test", "x86_64", "docker", "qemu"}),
                slots=2,
            ),
            ComputeNode(
                "github-x64-b",
                frozenset({"build", "git", "network", "python", "test", "x86_64", "docker", "qemu"}),
                slots=2,
            ),
            ComputeNode(
                "github-arm64",
                frozenset({"build", "git", "network", "python", "test", "arm64", "docker"}),
                slots=1,
            ),
            ComputeNode(
                "gpt-python",
                frozenset({"analysis", "comparison", "python", "small-simulation", "verification"}),
                slots=1,
            ),
        )
    )


def bootstrap_capsules() -> tuple[Capsule, ...]:
    return (
        Capsule(
            "pc-direct-uefi",
            "container",
            ("Projects/AurumPC/build-iso.sh",),
            frozenset({"build", "docker", "x86_64"}),
            outputs=("Aurum-PC-v0.01-amd64-direct-uefi.img",),
            posture="safe",
        ),
        Capsule(
            "pc-qemu-boot",
            "native",
            ("Projects/AurumVirtualLab/qemu-pc-direct-uefi.sh",),
            frozenset({"qemu", "test", "x86_64"}),
            dependencies=("pc-direct-uefi",),
            posture="verify",
        ),
        Capsule(
            "arm-portability",
            "container",
            ("python3", "-m", "unittest", "discover", "-s", "Projects/Codelation/tests"),
            frozenset({"arm64", "python", "test"}),
            posture="verify",
        ),
        Capsule(
            "state-space-analysis",
            "python",
            ("python3", "Projects/AurumPC/aurum_test_world.py"),
            frozenset({"analysis", "python"}),
            posture="adventurous",
        ),
    )


def _demo(root: Path) -> dict[str, Any]:
    store = ObjectStore(root)
    tree = store.snapshot({"hello": b"aurum\n"})
    commit = store.commit(tree, message="bootstrap machine substrate")
    store.update_ref("heads/bootstrap", commit)
    plan = default_farm().plan(bootstrap_capsules())
    return {
        "schema": SCHEMA,
        "object_store": {
            "tree": tree,
            "commit": commit,
            "ref": store.read_ref("heads/bootstrap"),
        },
        "farm": plan.as_dict(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aurum machine-native substrate")
    parser.add_argument("command", choices=("demo", "plan"))
    parser.add_argument("--store", default="")
    args = parser.parse_args(argv)

    if args.command == "plan":
        print(json.dumps(default_farm().plan(bootstrap_capsules()).as_dict(), indent=2, sort_keys=True))
        return 0

    if args.store:
        root = Path(args.store)
        root.mkdir(parents=True, exist_ok=True)
        report = _demo(root)
    else:
        with tempfile.TemporaryDirectory(prefix="aurum-machine-") as tmp:
            report = _demo(Path(tmp))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
