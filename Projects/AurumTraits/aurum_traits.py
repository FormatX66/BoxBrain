#!/usr/bin/env python3
"""Executable Generation-0 runtime for Aurum's mandatory human traits.

The runtime keeps stable trait identities while materializing a safe compatibility
provider on the current phenotype. Building a trait produces a deterministic,
seed-ready bundle; launching never uses a shell and internal recovery is read-only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCHEMA = "aurum-human-traits-v1"
BUNDLE_SCHEMA = "aurum-trait-bundle-v1"
REQUIRED = (
    "TR8:WEB",
    "TR8:FILES",
    "TR8:MEDIA",
    "TR8:WRITE",
    "TR8:INTENT",
    "TR8:CONNECT",
    "TR8:RECOVER",
)
INTERNAL_PROVIDERS = {"aurum-intent", "aurum-recovery"}
GARDEN_PLOTS = (
    "Documents",
    "Photos",
    "Music",
    "Videos",
    "Downloads",
    "Projects",
    "Shared",
)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def default_manifest() -> Path:
    return Path(__file__).with_name("traits.json")


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    source = (path or default_manifest()).resolve()
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ValueError(f"unexpected trait schema: {data.get('schema')!r}")
    traits = data.get("traits")
    if not isinstance(traits, list):
        raise ValueError("traits must be a list")
    by_id = {item.get("id"): item for item in traits if isinstance(item, dict)}
    missing = [trait_id for trait_id in REQUIRED if trait_id not in by_id]
    if missing:
        raise ValueError("missing mandatory traits: " + ", ".join(missing))
    for trait_id in REQUIRED:
        trait = by_id[trait_id]
        if not trait.get("goal"):
            raise ValueError(f"{trait_id}: missing goal")
        aliases = trait.get("human_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"{trait_id}: missing aliases")
        providers = trait.get("compatibility_providers")
        if not isinstance(providers, list) or not providers:
            raise ValueError(f"{trait_id}: missing providers")
    return data


def trait_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in data["traits"]}


def slug_for(trait_id: str) -> str:
    if trait_id not in REQUIRED:
        raise ValueError(f"unknown mandatory trait: {trait_id}")
    return trait_id.split(":", 1)[1].lower()


def resolve_provider(
    trait: dict[str, Any], *, search_path: str | None = None
) -> dict[str, Any] | None:
    for provider in trait["compatibility_providers"]:
        kind = provider.get("kind")
        command = provider.get("command")
        if kind == "internal" and command in INTERNAL_PROVIDERS:
            return {**provider, "resolved": command, "available": True}
        if kind == "executable" and isinstance(command, str):
            resolved = shutil.which(command, path=search_path)
            if resolved:
                return {**provider, "resolved": resolved, "available": True}
    return None


def provider_report(
    trait: dict[str, Any], *, search_path: str | None = None
) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for provider in trait["compatibility_providers"]:
        kind = provider.get("kind")
        command = provider.get("command")
        if kind == "internal":
            available = command in INTERNAL_PROVIDERS
            resolved = command if available else None
        else:
            resolved = shutil.which(str(command), path=search_path)
            available = bool(resolved)
        report.append({**provider, "available": available, "resolved": resolved})
    return report


def build_trait(
    trait_id: str, output: Path, *, manifest_path: Path | None = None
) -> Path:
    data = load_manifest(manifest_path)
    trait = trait_map(data)[trait_id]
    destination = output.resolve() / slug_for(trait_id)
    destination.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "generation": data.get("generation", 0),
        "trait": trait,
        "runtime": {
            "entrypoint": "aurum-trait",
            "module": "aurum_traits.py",
            "stage": "compatibility-runtime",
            "provider_selection": "first-available-declared-provider",
            "shell_execution": False,
        },
        "acceptance": {
            "bundle_validated": True,
            "provider_probe_required_on_target": True,
            "physical_use_verified": False,
        },
    }
    path = destination / "bundle.json"
    path.write_text(_canonical(bundle), encoding="utf-8")
    return path


def build_all(output: Path, *, manifest_path: Path | None = None) -> list[Path]:
    return [
        build_trait(trait_id, output, manifest_path=manifest_path)
        for trait_id in REQUIRED
    ]


def verify_bundle(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != BUNDLE_SCHEMA:
        raise ValueError("unexpected bundle schema")
    trait = data.get("trait")
    if not isinstance(trait, dict) or trait.get("id") not in REQUIRED:
        raise ValueError("bundle does not contain a mandatory trait")
    runtime = data.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("module") != "aurum_traits.py":
        raise ValueError("bundle runtime is missing")
    if runtime.get("shell_execution") is not False:
        raise ValueError("bundle must prohibit shell execution")
    providers = trait.get("compatibility_providers")
    if not isinstance(providers, list) or not providers:
        raise ValueError("bundle has no provider candidates")
    return data


def materialize_garden(root: Path) -> Path:
    base = root.expanduser().resolve()
    garden = base if base.name == "Garden" else base / "Garden"
    garden.mkdir(parents=True, exist_ok=True)
    for plot in GARDEN_PLOTS:
        (garden / plot).mkdir(exist_ok=True)
    metadata = {
        "schema": "aurum-garden-v1",
        "name": "Garden",
        "plots": list(GARDEN_PLOTS),
        "principle": (
            "Human things live here; storage mechanics remain below the projection."
        ),
    }
    (garden / ".aurum-garden.json").write_text(
        _canonical(metadata), encoding="utf-8"
    )
    return garden


def resolve_intent(
    text: str, *, manifest_path: Path | None = None
) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("intent text is empty")
    normalized = re.sub(r"\s+", " ", text.casefold()).strip()
    data = load_manifest(manifest_path)
    matches: list[tuple[int, str, str]] = []
    for trait in data["traits"]:
        for alias in trait["human_aliases"]:
            candidate = str(alias).casefold()
            if candidate in normalized:
                matches.append((len(candidate), trait["id"], alias))
    if not matches:
        fallback_words = {
            "open": "TR8:FILES",
            "play": "TR8:MEDIA",
            "watch": "TR8:MEDIA",
            "listen": "TR8:MEDIA",
            "browse": "TR8:WEB",
            "type": "TR8:WRITE",
            "save": "TR8:FILES",
        }
        for word, trait_id in fallback_words.items():
            if re.search(rf"\b{re.escape(word)}\b", normalized):
                return {
                    "trait_id": trait_id,
                    "matched": word,
                    "confidence": "fallback",
                }
        raise ValueError("no mandatory Aurum trait matched the intent")
    _, trait_id, alias = max(matches)
    return {"trait_id": trait_id, "matched": alias, "confidence": "alias"}


def recovery_status(state_root: Path) -> dict[str, Any]:
    root = state_root.expanduser().resolve()
    rollback_candidates = []
    for relative in ("rollback", "state/rollback", "state/mind/rollback"):
        candidate = root / relative
        if candidate.exists():
            rollback_candidates.append(str(candidate))
    known_good = []
    for pattern in ("*known-good*", "*generation*.json", "*checkpoint*.json"):
        known_good.extend(
            str(path) for path in root.glob(pattern) if path.is_file()
        )
    return {
        "schema": "aurum-recovery-status-v1",
        "state_root": str(root),
        "rollback_locations": sorted(set(rollback_candidates)),
        "known_good_evidence": sorted(set(known_good)),
        "actuation_performed": False,
    }


def _validated_url(target: str) -> str:
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("web target must be an http or https URL")
    return target


def launch_plan(
    trait_id: str,
    target: str | None,
    *,
    garden_root: Path,
    state_root: Path,
    search_path: str | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    data = load_manifest(manifest_path)
    trait = trait_map(data)[trait_id]
    provider = resolve_provider(trait, search_path=search_path)
    if provider is None:
        return {
            "trait_id": trait_id,
            "ready": False,
            "reason": "no-declared-provider-available",
            "providers": provider_report(trait, search_path=search_path),
        }

    command = provider["resolved"]
    if provider["kind"] == "internal":
        if command == "aurum-intent":
            if target is None:
                raise ValueError("intent provider requires text")
            return {
                "trait_id": trait_id,
                "ready": True,
                "internal": resolve_intent(target, manifest_path=manifest_path),
            }
        return {
            "trait_id": trait_id,
            "ready": True,
            "internal": recovery_status(state_root),
        }

    args = [str(command)]
    if trait_id == "TR8:WEB":
        args.append(_validated_url(target or "https://example.org"))
    elif trait_id == "TR8:FILES":
        garden = materialize_garden(garden_root)
        args.append(
            str(Path(target).expanduser().resolve()) if target else str(garden)
        )
    elif trait_id == "TR8:MEDIA":
        if target is None:
            raise ValueError("media provider requires a file or URL")
        if urlparse(target).scheme in {"http", "https"}:
            args.append(target)
        else:
            media = Path(target).expanduser().resolve()
            if not media.exists():
                raise ValueError("media target does not exist")
            args.append(str(media))
    elif trait_id == "TR8:WRITE":
        garden = materialize_garden(garden_root)
        document = (
            Path(target).expanduser().resolve()
            if target
            else garden / "Documents" / "Untitled.txt"
        )
        document.parent.mkdir(parents=True, exist_ok=True)
        document.touch(exist_ok=True)
        args.append(str(document))
    elif trait_id == "TR8:CONNECT" and Path(str(command)).name == "ip":
        args.extend(["-brief", "address"])
    return {
        "trait_id": trait_id,
        "ready": True,
        "provider": provider,
        "argv": args,
    }


def launch(plan: dict[str, Any], *, dry_run: bool) -> int:
    if not plan.get("ready"):
        return 3
    argv = plan.get("argv")
    if not argv or dry_run:
        return 0
    subprocess.Popen(argv, close_fds=True, start_new_session=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum human trait runtime")
    parser.add_argument("--manifest", type=Path, default=default_manifest())
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("validate")
    build = commands.add_parser("build")
    build.add_argument("--trait", required=True, choices=REQUIRED)
    build.add_argument("--output", type=Path, required=True)
    build_all_cmd = commands.add_parser("build-all")
    build_all_cmd.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify-bundle")
    verify.add_argument("--bundle", type=Path, required=True)
    garden = commands.add_parser("garden")
    garden.add_argument("--root", type=Path, required=True)
    intent = commands.add_parser("intent")
    intent.add_argument("text")
    probe = commands.add_parser("probe")
    probe.add_argument("--trait", required=True, choices=REQUIRED)
    probe.add_argument("--path")
    plan_cmd = commands.add_parser("plan")
    plan_cmd.add_argument("--trait", required=True, choices=REQUIRED)
    plan_cmd.add_argument("--target")
    plan_cmd.add_argument("--garden-root", type=Path, default=Path.home())
    plan_cmd.add_argument(
        "--state-root", type=Path, default=Path("/var/lib/aurum")
    )
    plan_cmd.add_argument("--path")
    plan_cmd.add_argument("--execute", action="store_true")

    args = parser.parse_args()
    if args.command == "validate":
        data = load_manifest(args.manifest)
        print(f"AURUM_TRAIT_RUNTIME_OK traits={len(data['traits'])}")
    elif args.command == "build":
        print(build_trait(args.trait, args.output, manifest_path=args.manifest))
    elif args.command == "build-all":
        for path in build_all(args.output, manifest_path=args.manifest):
            print(path)
    elif args.command == "verify-bundle":
        bundle = verify_bundle(args.bundle)
        print(f"AURUM_TRAIT_BUNDLE_OK trait={bundle['trait']['id']}")
    elif args.command == "garden":
        print(materialize_garden(args.root))
    elif args.command == "intent":
        print(
            _canonical(resolve_intent(args.text, manifest_path=args.manifest)),
            end="",
        )
    elif args.command == "probe":
        trait = trait_map(load_manifest(args.manifest))[args.trait]
        print(
            _canonical(
                {
                    "trait_id": args.trait,
                    "providers": provider_report(trait, search_path=args.path),
                }
            ),
            end="",
        )
    else:
        plan = launch_plan(
            args.trait,
            args.target,
            garden_root=args.garden_root,
            state_root=args.state_root,
            search_path=args.path,
            manifest_path=args.manifest,
        )
        print(_canonical(plan), end="")
        return launch(plan, dry_run=not args.execute)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"AURUM_TRAIT_ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
