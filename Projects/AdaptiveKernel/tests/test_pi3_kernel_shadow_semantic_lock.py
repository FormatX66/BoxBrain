from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[3]
SEMANTIC = REPO / "Projects" / "AdaptiveKernel" / "driver_candidates" / "generated" / "pi3-smsc95xx-nonbinding-candidate.c"
KERNEL = REPO / "Projects" / "AdaptiveKernel" / "driver_candidates" / "kernel_shadow" / "aurum_pi3_smsc95xx_kernel_shadow.c"
MANIFEST = REPO / "Projects" / "AdaptiveKernel" / "driver_candidates" / "kernel_shadow" / "candidate.json"

CONTRACT_DEFINES = (
    "AURUM_PARENT_VID",
    "AURUM_PARENT_PID",
    "AURUM_USB_VID",
    "AURUM_USB_PID",
    "AURUM_TX_OVERHEAD",
    "AURUM_TX_OVERHEAD_CSUM",
)
CONTRACT_FUNCTIONS = (
    "aurum_smsc95xx_init",
    "aurum_smsc95xx_set_link",
    "aurum_smsc95xx_set_rx_checksum",
    "aurum_smsc95xx_tx_frame_len",
)


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def parse_unsigned_literal(value: str) -> int:
    return int(value.rstrip("uU"), 0)


def extract_defines(source: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for name in CONTRACT_DEFINES:
        match = re.search(
            rf"(?m)^\s*#define\s+{re.escape(name)}\s+((?:0[xX][0-9a-fA-F]+|[0-9]+)[uU]?)\s*$",
            source,
        )
        if match is None:
            raise AssertionError(f"missing contract define: {name}")
        values[name] = parse_unsigned_literal(match.group(1))
    return values


def extract_speed_envelope(source: str) -> tuple[int, ...]:
    values = sorted({int(value) for value in re.findall(r"speed_mbps\s*!=\s*([0-9]+)[uU]?", source)})
    if not values:
        raise AssertionError("missing speed envelope")
    return tuple(values)


class KernelShadowSemanticLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.semantic_bytes = SEMANTIC.read_bytes()
        self.semantic = self.semantic_bytes.decode("utf-8")
        self.kernel = KERNEL.read_text(encoding="utf-8")
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_binds_exact_semantic_candidate_blob(self):
        expected = self.manifest["basis"]["semantic_source_git_blob_sha1"]
        self.assertEqual(git_blob_sha1(self.semantic_bytes), expected)

    def test_kernel_shadow_constants_match_sealed_semantic_candidate(self):
        self.assertEqual(extract_defines(self.kernel), extract_defines(self.semantic))

    def test_kernel_shadow_speed_envelope_matches_sealed_semantic_candidate(self):
        self.assertEqual(extract_speed_envelope(self.kernel), extract_speed_envelope(self.semantic))
        self.assertEqual(extract_speed_envelope(self.kernel), (10, 100))

    def test_kernel_shadow_maps_every_sealed_core_function(self):
        for function in CONTRACT_FUNCTIONS:
            self.assertIn(function, self.semantic)
            self.assertIn(function, self.kernel)

    def test_kernel_lowering_is_type_narrowing_not_authority_expansion(self):
        # The host candidate accepts integer booleans and explicitly rejects invalid
        # values. The kernel-shaped translation narrows those inputs to bool; it must
        # not compensate for that narrowing by adding a broader runtime surface.
        self.assertIn("int full_duplex", self.semantic)
        self.assertIn("int enabled", self.semantic)
        self.assertIn("int checksum_partial", self.semantic)
        self.assertIn("bool full_duplex", self.kernel)
        self.assertIn("bool enabled", self.kernel)
        self.assertIn("bool checksum_partial", self.kernel)
        self.assertNotIn("struct usb_driver", self.kernel)
        self.assertNotIn("MODULE_DEVICE_TABLE", self.kernel)
        self.assertNotIn("usb_submit_urb", self.kernel)
        self.assertNotIn("usb_control_msg", self.kernel)

    def test_contract_would_detect_rebound_semantic_constant_drift(self):
        # This specifically covers the gap where the manifest could later be
        # deliberately rebound to a new semantic blob. Source identity alone would
        # then pass; the semantic lock must still reject an unpropagated constant.
        changed = self.semantic.replace("#define AURUM_TX_OVERHEAD 8u", "#define AURUM_TX_OVERHEAD 9u", 1)
        self.assertNotEqual(extract_defines(self.kernel), extract_defines(changed))

    def test_contract_would_detect_rebound_speed_envelope_drift(self):
        changed = self.semantic.replace("speed_mbps != 100u", "speed_mbps != 1000u", 1)
        self.assertNotEqual(extract_speed_envelope(self.kernel), extract_speed_envelope(changed))


if __name__ == "__main__":
    unittest.main()
