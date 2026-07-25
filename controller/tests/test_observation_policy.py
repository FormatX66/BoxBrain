import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from boxbrain_controller.observation_policy import ObservationPolicy
from boxbrain_controller.sandbox_observer import (
    NormalizedRedactionRegion,
    apply_redactions,
)


def test_policy_loads_strict_zero_retention_defaults(tmp_path: Path) -> None:
    policy_path = tmp_path / "observation.json"
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "max_frame_width": 1280,
                "max_frame_bytes": 8 * 1024 * 1024,
                "redaction_regions": [],
                "evidence_retention": {
                    "mode": "none",
                    "max_frames": 0,
                    "max_age_seconds": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    policy = ObservationPolicy.load(policy_path)

    assert policy.evidence_retention.mode == "none"
    assert policy.evidence_retention.max_frames == 0
    assert policy.summary()["redaction_region_count"] == 0


def test_policy_rejects_region_outside_frame() -> None:
    with pytest.raises(ValidationError, match="inside the frame"):
        ObservationPolicy.model_validate(
            {
                "redaction_regions": [
                    {
                        "id": "outside",
                        "x": 0.8,
                        "y": 0.1,
                        "width": 0.3,
                        "height": 0.2,
                        "fill": "black",
                    }
                ]
            }
        )


def test_policy_rejects_nonzero_or_unknown_retention() -> None:
    with pytest.raises(ValidationError):
        ObservationPolicy.model_validate(
            {
                "evidence_retention": {
                    "mode": "bounded",
                    "max_frames": 1,
                    "max_age_seconds": 60,
                }
            }
        )


def test_redaction_masks_only_the_configured_pixels() -> None:
    image = Image.new("RGB", (100, 50), color="white")

    apply_redactions(
        image,
        (
            NormalizedRedactionRegion(
                x=0.25,
                y=0.2,
                width=0.5,
                height=0.4,
            ),
        ),
    )

    assert image.getpixel((25, 10)) == (0, 0, 0)
    assert image.getpixel((74, 29)) == (0, 0, 0)
    assert image.getpixel((24, 10)) == (255, 255, 255)
    assert image.getpixel((75, 30)) == (255, 255, 255)
