from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]


def load(name: str):
    path = ROOT / name
    spec = importlib.util.spec_from_file_location(f"test_{name.replace('.', '_')}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AurumAIControlPlaneTests(unittest.TestCase):
    def test_control_plane_exposes_all_os_domains_through_policy_broker(self) -> None:
        module = load("aurum_control_plane.py")
        catalog = module.catalog()
        self.assertEqual(catalog["schema"], "aurum.control-plane.v1")
        self.assertEqual(catalog["scope"], "all-os-domains")
        self.assertEqual(catalog["model_intent_scope"], "full")
        self.assertEqual(catalog["execution_authority"], "aurum-policy-broker")
        domains = {item["id"] for item in catalog["domains"]}
        for required in {"appearance", "interaction", "traits", "build", "runtime", "kernel", "devices", "transport", "storage", "identity", "permissions", "recovery", "power"}:
            self.assertIn(required, domains)
        request = module.request("appearance", "make the desktop denser")
        self.assertTrue(request["requires_authorization"])
        self.assertTrue(request["requires_verification"])
        self.assertFalse(request["direct_shell_contract"])

    def test_registry_uses_trait_terminology_and_keeps_gpt_resident(self) -> None:
        module = load("aurum_traits.py")
        summary = module.summary()
        ids = {item["id"] for item in summary["traits"]}
        self.assertIn("TRAIT:GPT", ids)
        self.assertTrue(all(not item.startswith("TR8:") for item in ids))
        self.assertIn("CORE:CONTROL", {item["id"] for item in summary["resident_capabilities"]})
        self.assertTrue(module.trait("TRAIT:GPT")["resident"])

    def test_gpt_trait_reports_bounded_direct_execution_without_raw_shell(self) -> None:
        module = load("aurum_gpt_trait.py")
        with patch.object(module, "_api_key", return_value=None):
            current = module.status()
        self.assertEqual(current["trait"], "GPT")
        self.assertEqual(current["control_scope"], "all-os-domains")
        self.assertEqual(current["model_intent_scope"], "full")
        self.assertEqual(current["execution_authority"], "aurum-policy-broker")
        self.assertEqual(current["host_actuation"], "bounded")
        self.assertTrue(current["function_tools"])
        self.assertTrue(current["workspace_read"])
        self.assertFalse(current["workspace_exact_replace"])
        self.assertTrue(current["appearance_preview"])
        self.assertTrue(current["appearance_resets_on_reboot"])
        self.assertFalse(current["raw_shell"])
        self.assertFalse(current["git_push"])
        self.assertEqual(current["status"], "api-key-required")


if __name__ == "__main__":
    unittest.main()
