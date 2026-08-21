#!/usr/bin/env python3
"""Validate the mandatory human-capability contract carried by every Aurum seed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED = {
    "TR8:WEB",
    "TR8:FILES",
    "TR8:MEDIA",
    "TR8:WRITE",
    "TR8:INTENT",
    "TR8:CONNECT",
    "TR8:RECOVER",
}


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "aurum-human-traits-v1":
        raise SystemExit(f"unexpected schema: {data.get('schema')!r}")
    return data


def validate(data: dict, only: str | None = None) -> list[str]:
    traits = data.get("traits")
    if not isinstance(traits, list):
        raise SystemExit("traits must be a list")
    by_id = {item.get("id"): item for item in traits if isinstance(item, dict)}
    missing = REQUIRED - set(by_id)
    if missing:
        raise SystemExit("missing mandatory seed traits: " + ", ".join(sorted(missing)))

    targets = [only] if only else sorted(REQUIRED)
    for trait_id in targets:
        if trait_id not in REQUIRED:
            raise SystemExit(f"unknown required trait: {trait_id}")
        trait = by_id[trait_id]
        if not trait.get("goal"):
            raise SystemExit(f"{trait_id}: missing goal")
        aliases = trait.get("human_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise SystemExit(f"{trait_id}: missing human aliases")
        providers = trait.get("compatibility_providers")
        if not isinstance(providers, list) or not providers:
            raise SystemExit(f"{trait_id}: missing staged compatibility provider contract")
    return targets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(Path(__file__).with_name("traits.json")))
    parser.add_argument("--trait", help="validate one required trait while still enforcing the complete seed set")
    args = parser.parse_args()

    targets = validate(load_manifest(Path(args.manifest)), args.trait)
    print("AURUM_TRAITS_OK complete_seed_contract=true traits=" + ",".join(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
