from __future__ import annotations

import json
import unittest
from pathlib import Path

from pi3_completion_projection import project_pi3_completion


class Pi3CompletionProjectionTests(unittest.TestCase):
    def plan(self):
        return {
            "schema": "aurum-completion-plan-v1",
            "gates": [
                {
                    "id": "pi3-kernel-canary",
                    "state": "held-on-kernel-mutation-prerequisites",
                    "ready_now": False,
                    "proof": "old proof",
                }
            ],
        }

    def shared(self, *, watchdog=False):
        return {
            "schema": "aurum-shared-state-v1",
            "subjects": {
                "pi3-kernel-canary-preflight-1": {
                    "source": "github-pi3-kernel-canary-preflight",
                    "timestamp": "2026-08-26T03:29:40+00:00",
                    "payload": {
                        "kernel": "6.18.34+rpt-rpi-v8",
                        "matching_headers_present": True,
                        "module_symvers_present": True,
                        "compile_only_canary_passed": True,
                        "module_loaded": False,
                        "system_driver_changed": False,
                        "out_of_band_watchdog_proven": watchdog,
                        "workflow_conclusion": "success",
                    },
                }
            },
        }

    def test_exact_compile_prerequisites_remove_only_that_blocker(self):
        projected, changed = project_pi3_completion(self.plan(), self.shared())
        gate = projected["gates"][0]
        self.assertTrue(changed)
        self.assertEqual(gate["state"], "held-on-watchdog-and-kernel-authority")
        self.assertIn("matching headers, Module.symvers, and inert compile-only canary are proven", gate["proof"])
        self.assertIn("out-of-band watchdog/recovery path", gate["proof"])
        self.assertFalse(gate["ready_now"])

    def test_watchdog_evidence_still_cannot_grant_kernel_authority(self):
        projected, _ = project_pi3_completion(self.plan(), self.shared(watchdog=True))
        gate = projected["gates"][0]
        self.assertEqual(gate["state"], "held-on-explicit-kernel-mutation-authority")
        self.assertFalse(gate["ready_now"])
        self.assertIn("fresh explicit kernel-mutation authority", gate["proof"])

    def test_incomplete_or_mutating_preflight_cannot_advance_gate(self):
        shared = self.shared()
        shared["subjects"]["pi3-kernel-canary-preflight-1"]["payload"]["module_loaded"] = True
        projected, changed = project_pi3_completion(self.plan(), shared)
        self.assertFalse(changed)
        self.assertEqual(projected["gates"][0]["state"], "held-on-kernel-mutation-prerequisites")

    def test_current_repository_evidence_projects_without_granting_authority(self):
        repo_root = Path(__file__).resolve().parents[3]
        plan = json.loads((repo_root / "Projects" / "Aurum" / "completion-plan.json").read_text(encoding="utf-8-sig"))
        shared = json.loads((repo_root / "Projects" / "Aurum" / "shared-state" / "CURRENT_STATE.json").read_text(encoding="utf-8-sig"))
        projected, _ = project_pi3_completion(plan, shared)
        gate = next(item for item in projected["gates"] if item.get("id") == "pi3-kernel-canary")
        self.assertIn(gate["state"], {"held-on-watchdog-and-kernel-authority", "held-on-explicit-kernel-mutation-authority"})
        self.assertFalse(gate["ready_now"])
        self.assertIn("Module.symvers", gate["proof"])


if __name__ == "__main__":
    unittest.main()
