import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import PluginSummary


class PluginRegistry:
    """Discovers plugin manifests without importing or executing plugin code."""

    def __init__(self, plugin_dir: Path) -> None:
        self._plugin_dir = plugin_dir

    def discover(self) -> list[PluginSummary]:
        if not self._plugin_dir.is_dir():
            return []

        plugins: list[PluginSummary] = []
        for manifest_path in sorted(
            self._plugin_dir.glob("*/boxbrain_plugin.json")
        ):
            plugin = self._read_manifest(manifest_path)
            if plugin is not None:
                plugins.append(plugin)
        return plugins

    @staticmethod
    def _read_manifest(path: Path) -> PluginSummary | None:
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            return PluginSummary.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError):
            return None

