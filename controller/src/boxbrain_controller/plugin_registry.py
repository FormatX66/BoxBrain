import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from .models import PluginSummary


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=3,
        max_length=120,
        pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$",
    )
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(
        pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$",
    )
    description: str = Field(min_length=1, max_length=500)
    enabled: bool = False
    protocol_version: Literal["1"]
    entrypoint: str
    capabilities: tuple[str, ...] = Field(min_length=1, max_length=32)
    process_boundary: Literal["manifest-only", "out-of-process"]
    target_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )

    @field_validator("entrypoint")
    @classmethod
    def entrypoint_must_be_a_local_python_file(cls, value: str) -> str:
        if (
            "/" in value
            or "\\" in value
            or Path(value).suffix.lower() != ".py"
            or Path(value).name != value
        ):
            raise ValueError("entrypoint must be a local Python filename")
        return value

    @field_validator("capabilities")
    @classmethod
    def capabilities_must_be_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("capabilities must be unique")
        if any(
            not capability
            or len(capability) > 120
            or capability.strip() != capability
            for capability in value
        ):
            raise ValueError("capabilities must be non-empty normalized names")
        return value

    def summary(self) -> PluginSummary:
        return PluginSummary(
            id=self.id,
            name=self.name,
            version=self.version,
            description=self.description,
            enabled=self.enabled,
            protocol_version=self.protocol_version,
            capabilities=self.capabilities,
            process_boundary=self.process_boundary,
            target_id=self.target_id,
        )


@dataclass(frozen=True, slots=True)
class RegisteredPlugin:
    manifest: PluginManifest
    directory: Path
    entrypoint: Path


class PluginRegistry:
    """Discovers strict manifests without importing or executing plugin code."""

    def __init__(self, plugin_dir: Path) -> None:
        self._plugin_dir = plugin_dir

    def discover(self) -> list[PluginSummary]:
        return [
            registration.manifest.summary()
            for registration in self._registrations()
        ]

    def get(self, plugin_id: str) -> RegisteredPlugin | None:
        return next(
            (
                registration
                for registration in self._registrations()
                if registration.manifest.id == plugin_id
            ),
            None,
        )

    def _registrations(self) -> list[RegisteredPlugin]:
        if not self._plugin_dir.is_dir():
            return []

        plugins: list[RegisteredPlugin] = []
        for manifest_path in sorted(
            self._plugin_dir.glob("*/boxbrain_plugin.json")
        ):
            plugin = self._read_manifest(manifest_path)
            if plugin is not None:
                plugins.append(plugin)
        return plugins

    @staticmethod
    def _read_manifest(path: Path) -> RegisteredPlugin | None:
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
            manifest = PluginManifest.model_validate(payload)
            directory = path.parent.resolve()
            entrypoint = (directory / manifest.entrypoint).resolve()
            if entrypoint.parent != directory or not entrypoint.is_file():
                return None
            return RegisteredPlugin(
                manifest=manifest,
                directory=directory,
                entrypoint=entrypoint,
            )
        except (OSError, json.JSONDecodeError, ValidationError):
            return None
