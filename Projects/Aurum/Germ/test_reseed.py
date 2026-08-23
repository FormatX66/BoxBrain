#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import reseed


class ReseedGermTests(unittest.TestCase):
    def test_repository_manifest_is_compatible(self) -> None:
        manifest = reseed.load_manifest(Path(__file__).with_name("GENETICS.json"))
        self.assertEqual(manifest["schema"], reseed.SCHEMA)
        self.assertEqual(manifest["repository"], reseed.REPOSITORY)
        self.assertTrue(manifest["policy"]["candidate_only_staging"])
        self.assertFalse(manifest["policy"]["live_overwrite_allowed"])
        self.assertTrue(manifest["policy"]["promotion_requires_health_evidence"])

    def test_unknown_schema_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "GENETICS.json"
            path.write_text(json.dumps({"schema": "future", "repository": reseed.REPOSITORY}), encoding="utf-8")
            with self.assertRaises(reseed.GermError):
                reseed.load_manifest(path)

    def test_wrong_repository_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "GENETICS.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": reseed.SCHEMA,
                        "germ_protocol": reseed.GERM_PROTOCOL,
                        "repository": "https://example.invalid/not-aurum.git",
                        "required_paths": ["x"],
                        "policy": {
                            "candidate_only_staging": True,
                            "live_overwrite_allowed": False,
                            "promotion_requires_health_evidence": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(reseed.GermError):
                reseed.load_manifest(path)

    def test_stage_requires_explicit_network_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(reseed.GermError):
                reseed.stage(ref="main", state_root=Path(td), authorize_network=False)

    def test_plan_never_claims_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            payload = reseed.plan("main", Path(td))
            self.assertIn("live-overwrite", payload["this_tool_does_not_perform"])
            self.assertIn("candidate-promotion", payload["this_tool_does_not_perform"])

    def test_candidate_verification_records_immutable_commit(self) -> None:
        source_manifest = json.loads(Path(__file__).with_name("GENETICS.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "candidate"
            root.mkdir()
            for relative in source_manifest["required_paths"]:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative.endswith("GENETICS.json"):
                    path.write_text(json.dumps(source_manifest), encoding="utf-8")
                else:
                    path.write_text("test fixture\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "germ-test@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Aurum Germ Test"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=root, check=True)
            verified = reseed.verify_candidate(root)
            self.assertRegex(verified["commit"], r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
