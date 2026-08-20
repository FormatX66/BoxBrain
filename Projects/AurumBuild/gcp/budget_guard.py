#!/usr/bin/env python3
"""Refuse GCP burst work before the reserved free-tier ceiling is crossed."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def consumed_seconds(builds: list[dict], *, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    total = 0.0
    for build in builds:
        start = build.get("startTime")
        if not start:
            continue
        finish = build.get("finishTime")
        end = datetime.fromisoformat(finish.replace("Z", "+00:00")) if finish else now
        total += (end - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
    return max(0.0, total)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("builds", type=Path)
    parser.add_argument("--limit-minutes", type=int, default=2000)
    parser.add_argument("--reserve-minutes", type=int, default=15)
    args = parser.parse_args()
    builds = json.loads(args.builds.read_text(encoding="utf-8"))
    seconds = consumed_seconds(builds)
    projected = seconds + max(0, args.reserve_minutes) * 60
    print(
        "AURUM_GCP_MONTHLY_USAGE "
        f"minutes={seconds / 60:.2f} projected={projected / 60:.2f} limit={args.limit_minutes}"
    )
    return 2 if projected >= args.limit_minutes * 60 else 0


if __name__ == "__main__":
    raise SystemExit(main())
