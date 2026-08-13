from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEPLOYER = Path("installer/deploy-aurum-live-to-pi.ps1")
WATCHER = Path("installer/aurum-local-lane/watch-aurum-local-lane.ps1")
CODELATION = Path("Projects/Codelation")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def codelation_tree_hash(repo: Path) -> str:
    root = repo / CODELATION
    if not root.is_dir():
        raise FileNotFoundError(f"Codelation source is missing: {root}")
    rows: list[str] = []
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in files:
        relative = path.relative_to(root).as_posix()
        rows.append(f"{relative}|{sha256_file(path)}")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def inspect(config: dict[str, Any], repo: Path | None = None) -> dict[str, Any]:
    if int(config.get("schema_version", 0)) != 1:
        raise ValueError("Aurum lane configuration schema is unsupported.")
    root = Path(repo or config.get("repository_root", "")).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Aurum lane repository is unavailable: {root}")

    checks = {
        "deployer_sha256": {
            "approved": str(config.get("approved_deployer_sha256", "")),
            "actual": sha256_file(root / DEPLOYER),
        },
        "codelation_tree_sha256": {
            "approved": str(config.get("approved_codelation_tree_sha256", "")),
            "actual": codelation_tree_hash(root),
        },
        "watcher_sha256": {
            "approved": str(config.get("approved_watcher_sha256", "")),
            "actual": sha256_file(root / WATCHER),
        },
    }
    drift: list[str] = []
    for name, values in checks.items():
        values["match"] = bool(values["approved"]) and values["approved"].lower() == values["actual"].lower()
        if not values["match"]:
            drift.append(name)

    return {
        "schema_version": 1,
        "repository_root": str(root),
        "approved_commit": str(config.get("approved_commit", "")),
        "checks": checks,
        "drift": drift,
        "approval_current": not drift,
        "reapproval_required": bool(drift),
        "read_only": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Aurum local-lane approval drift inspection."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--repo", type=Path)
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        result = inspect(config, args.repo)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
    return 0 if result["approval_current"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
