from __future__ import annotations

import unittest
from pathlib import Path


BUILDER = Path(__file__).parents[1] / "build-direct-uefi-image.sh"
WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "aurum-pc-v001.yml"


class DirectUefiChecksumContractTests(unittest.TestCase):
    def test_checksum_path_survives_container_to_host_boundary(self) -> None:
        builder = BUILDER.read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")

        # The image is constructed inside a container as /workspace/dist/..., but
        # GitHub verifies the checksum from the host repository root. Never write
        # the container-absolute image path into the checksum manifest.
        self.assertNotIn(
            'sha256sum "$OUTPUT_IMAGE" > "$OUTPUT_IMAGE.sha256"',
            builder,
        )
        self.assertIn('OUTPUT_PARENT=$(dirname "$OUTPUT_DIR")', builder)
        self.assertIn('OUTPUT_DIR_NAME=$(basename "$OUTPUT_DIR")', builder)
        self.assertIn('cd "$OUTPUT_PARENT"', builder)
        self.assertIn(
            'sha256sum "$OUTPUT_DIR_NAME/$OUTPUT_NAME" > "$OUTPUT_DIR_NAME/$OUTPUT_NAME.sha256"',
            builder,
        )
        self.assertIn(
            "sha256sum -c dist/Aurum-PC-v0.01-amd64-direct-uefi.img.sha256",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
