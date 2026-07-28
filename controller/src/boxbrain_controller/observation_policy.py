from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class RedactionRegion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    fill: Literal["black"] = "black"

    @model_validator(mode="after")
    def require_region_inside_frame(self) -> RedactionRegion:
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("Redaction region must remain inside the frame.")
        return self


class EvidenceRetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    mode: Literal["none"] = "none"
    max_frames: Literal[0] = 0
    max_age_seconds: Literal[0] = 0


class ObservationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    max_frame_width: int = Field(default=1280, ge=320, le=1600)
    max_frame_bytes: int = Field(
        default=8 * 1024 * 1024,
        ge=64 * 1024,
        le=8 * 1024 * 1024,
    )
    redaction_regions: tuple[RedactionRegion, ...] = Field(
        default=(),
        max_length=32,
    )
    evidence_retention: EvidenceRetentionPolicy = Field(
        default_factory=EvidenceRetentionPolicy
    )

    @field_validator("redaction_regions", mode="before")
    @classmethod
    def normalize_json_regions(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def require_unique_region_ids(self) -> ObservationPolicy:
        region_ids = [region.id for region in self.redaction_regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("Redaction region ids must be unique.")
        return self

    @classmethod
    def load(cls, path: str | Path) -> ObservationPolicy:
        policy_path = Path(path)
        try:
            payload = json.loads(policy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Observation policy could not be loaded from {policy_path}."
            ) from error
        return cls.model_validate(payload)

    def summary(self) -> dict[str, object]:
        return {
            "max_frame_width": self.max_frame_width,
            "max_frame_bytes": self.max_frame_bytes,
            "redaction_region_count": len(self.redaction_regions),
            "evidence_retention": self.evidence_retention.mode,
            "max_retained_frames": self.evidence_retention.max_frames,
            "retention_max_age_seconds": (
                self.evidence_retention.max_age_seconds
            ),
        }
