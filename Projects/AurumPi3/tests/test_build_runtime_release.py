from __future__ import annotations

import importlib.util
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = PROJECT.parents[1]
sys.path.insert(0, str(PROJECT))

MODULE_PATH = PROJECT / "build-runtime-release.py"
SPEC = importlib.util.spec_from_file_location("build_runtime_release", MODULE_PATH)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

from aurum_release_gate import REQUIRED_EVIDENCE, converge_evidence, evidence_document


class BuildRuntimeReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.commit = "1" * 40
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.proof_path = self.root / "convergence.json"
        proof = converge_evidence(
            [evidence_document(name, self.commit) for name in REQUIRED_EVIDENCE], self.commit
        )
        self.proof_path.write_text(json.dumps(proof), encoding="utf-8")

    def test_release_contains_capabilities_updater_and_same_commit_proof(self) -> None:
        with mock.patch.object(builder, "source_revision", return_value=self.commit):
            artifact, manifest_path, _pin = builder.build_release(
                REPOSITORY,
                self.root / "dist",
                "0.03.0",
                "0.03.0-test",
                None,
                self.proof_path,
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_commit"], self.commit)
        self.assertEqual(manifest["verification"]["convergence"]["commit"], self.commit)
        self.assertIn("health", manifest["capabilities"])
        with tarfile.open(artifact, "r:gz") as archive:
            names = set(archive.getnames())
        self.assertIn("payload/aurum_pi3_console.py", names)
        self.assertIn("payload/aurum_updater.py", names)
        self.assertIn("payload/aurum_release_gate.py", names)
        self.assertIn("payload/codelation/field", names)

    def test_release_refuses_a_proof_from_another_commit(self) -> None:
        bad = converge_evidence(
            [evidence_document(name, "2" * 40) for name in REQUIRED_EVIDENCE], "2" * 40
        )
        self.proof_path.write_text(json.dumps(bad), encoding="utf-8")
        with mock.patch.object(builder, "source_revision", return_value=self.commit):
            with self.assertRaisesRegex(SystemExit, "same-commit convergence proof is required"):
                builder.build_release(
                    REPOSITORY,
                    self.root / "dist",
                    "0.03.0",
                    "0.03.0-test",
                    None,
                    self.proof_path,
                )


if __name__ == "__main__":
    unittest.main()
