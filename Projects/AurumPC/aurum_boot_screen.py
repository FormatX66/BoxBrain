#!/usr/bin/env python3
"""Dependency-free VT loading screen for Aurum PC startup."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import TextIO

SCHEMA = "aurum.boot-screen.v1"
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state")) / "boot-screen.json"
STAGES = (
    ("hardware", "Learning this machine"),
    ("input", "Waking mouse and trackpad"),
    ("network", "Bringing connections online"),
    ("workspace", "Preparing the Aurum workspace"),
    ("verification", "Checking the local build"),
    ("desktop", "Starting the Hopper desktop"),
)
VALID_STATUS = frozenset({"pending", "active", "ready", "degraded", "failed", "skipped"})


class BootScreen:
    def __init__(
        self,
        *,
        output: TextIO = sys.stdout,
        state_path: Path = DEFAULT_STATE,
        enabled: bool | None = None,
    ) -> None:
        self.output = output
        self.state_path = state_path
        self.enabled = output.isatty() if enabled is None else enabled
        self.states = {name: "pending" for name, _ in STAGES}
        self.details = {name: "" for name, _ in STAGES}
        self.overall = "starting"
        self._persist()

    @staticmethod
    def _detail(value: object) -> str:
        text = " ".join(str(value or "").split())
        return text[:96]

    def update(self, stage: str, status: str, detail: object = "") -> None:
        if stage not in self.states:
            raise ValueError(f"unknown boot screen stage: {stage}")
        if status not in VALID_STATUS:
            raise ValueError(f"invalid boot screen status: {status}")
        self.states[stage] = status
        self.details[stage] = self._detail(detail)
        self._persist()
        self.render()

    def finish(self, status: str = "ready", detail: object = "") -> None:
        if status not in {"ready", "degraded", "failed"}:
            raise ValueError(f"invalid boot screen completion: {status}")
        self.overall = status
        if detail:
            self.details["desktop"] = self._detail(detail)
        self._persist()
        self.render()

    def payload(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "machine": "Hopper",
            "status": self.overall,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "stages": [
                {"id": name, "label": label, "status": self.states[name], "detail": self.details[name]}
                for name, label in STAGES
            ],
        }

    def _persist(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.state_path.with_name(f".{self.state_path.name}.{os.getpid()}.tmp")
            temporary.write_text(json.dumps(self.payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temporary, self.state_path)
        except OSError:
            # A display aid must never become a boot dependency.
            return

    def render(self) -> None:
        if not self.enabled:
            return
        marks = {
            "pending": "·",
            "active": "◆",
            "ready": "✓",
            "degraded": "!",
            "failed": "×",
            "skipped": "–",
        }
        lines = [
            "\x1b[2J\x1b[H",
            "",
            "                         A U R U M",
            "",
            "                 Waking Hopper · Gen 0 → Gen 1",
            "",
        ]
        for name, label in STAGES:
            detail = f"  {self.details[name]}" if self.details[name] else ""
            lines.append(f"              {marks[self.states[name]]}  {label}{detail}")
        lines.extend(
            [
                "",
                "             Recovery console remains available on Ctrl+Alt+F1",
                "" if self.overall == "starting" else f"                         {self.overall.upper()}",
            ]
        )
        self.output.write("\n".join(lines) + "\n")
        self.output.flush()
