#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import virtual_x86_gate


ROOT = Path(__file__).resolve().parents[3]
BUILD = Path(__file__).with_name("build-x86-tinyseed.sh")
WORKFLOW = ROOT / ".github/workflows/aurum-tiny-seed-x86.yml"


class TinySeedBootContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.build = BUILD.read_text(encoding="utf-8")

    def test_bootloaders_are_text_only_and_have_three_modes(self) -> None:
        self.assertNotIn("vesamenu.c32", self.build)
        self.assertNotIn("gfxterm", self.build)
        self.assertNotIn("menu.c32", self.build)
        self.assertIn("say AURUM TINY SEED", self.build)
        self.assertIn("label safe", self.build)
        self.assertIn("label spoken", self.build)
        self.assertIn("insmod all_video", self.build)
        self.assertIn("set gfxpayload=keep", self.build)
        self.assertIn('menuentry "Aurum Tiny Seed"', self.build)
        self.assertIn('menuentry "Aurum Tiny Seed (safe verbose)"', self.build)
        self.assertIn('menuentry "Aurum Tiny Seed (spoken / blind)"', self.build)

    def test_graphics_handoff_is_disabled_in_every_boot_family(self) -> None:
        self.assertGreaterEqual(self.build.count("plymouth.enable=0"), 7)
        self.assertIn("aurum.ui=compact", self.build)
        self.assertIn("aurum.ui=plain nomodeset", self.build)

    def test_spoken_mode_has_runtime_and_service(self) -> None:
        for expected in (
            "espeakup",
            "speakup.synth=soft",
            "aurum-accessibility.service",
            "ConditionKernelCommandLine=aurum.accessibility=blind",
            "espeakup.service.d/aurum-blind-only.conf",
            "accessibility.py",
        ):
            self.assertIn(expected, self.build)

    def test_diskless_diagnostics_is_a_stable_waiting_state(self) -> None:
        self.assertIn("SuccessExitStatus=3", self.build)

    def test_workflow_requires_sync_accessibility_and_framebuffer_proof(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for expected in (
            "repository_https=true repository_sync=true",
            "AURUM_TINYSEED_ACCESSIBILITY_READY",
            "virtual_x86_gate.py",
            "tinyseed-uefi.ppm",
            "tinyseed-spoken.ppm",
        ):
            self.assertIn(expected, workflow)

    def test_ppm_gate_distinguishes_visible_color_from_blank(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proof.ppm"
            pixels = bytes((0, 0, 0, 255, 215, 95, 51, 214, 255, 208, 208, 208))
            path.write_bytes(b"P6\n4 1\n255\n" + pixels)
            metrics = virtual_x86_gate._ppm_metrics(path)
        self.assertEqual(metrics["unique_colors"], 4)
        self.assertEqual(metrics["visible_pixels"], 3)


if __name__ == "__main__":
    unittest.main()
