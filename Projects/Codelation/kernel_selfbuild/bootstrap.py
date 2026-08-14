from __future__ import annotations

import argparse
import json
from pathlib import Path

from .driver_plan import build_driver_plan
from .hardware_profile import collect_machine_profile
from .kernel_plan import make_kernel_build_plan


def emit_bootstrap_state(output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = collect_machine_profile()
    driver_plan = build_driver_plan(profile)
    build_plan = make_kernel_build_plan(profile, driver_plan)

    profile_path = output_dir / "machine-profile.json"
    plan_path = output_dir / "kernel-build-plan.json"
    profile_path.write_text(json.dumps(profile.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    plan_path.write_text(
        json.dumps(
            {
                **build_plan.to_dict(),
                "driver_work_items": [item.to_dict() for item in driver_plan],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return profile_path, plan_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile this Linux seed boot and emit an Aurum machine-specific kernel build plan.")
    parser.add_argument("--output-dir", default="aurum-kernel-state")
    args = parser.parse_args()
    profile_path, plan_path = emit_bootstrap_state(Path(args.output_dir))
    print(profile_path)
    print(plan_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
