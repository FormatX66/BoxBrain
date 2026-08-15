from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

import aurum_pi3_update as updater


def load_builder():
    path = PROJECT / "build-update-bundle.py"
    spec = importlib.util.spec_from_file_location("aurum_pi3_build_update", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AurumPi3UpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dist = self.root / "dist"
        _, self.manifest, self.digest_file = load_builder().build(PROJECT, self.dist)
        self.manifest_sha = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def test_bundle_is_deterministic_and_inspectable(self) -> None:
        first_bundle = (self.dist / "Aurum-Pi3-v0.01-capability-update.tar.gz").read_bytes()
        inspection = updater.inspect_update(str(self.manifest), self.manifest_sha)
        self.assertTrue(inspection["verified"])
        self.assertFalse(inspection["installed"])
        self.assertEqual(len(inspection["files"]), 2)
        load_builder().build(PROJECT, self.dist)
        second_bundle = (self.dist / "Aurum-Pi3-v0.01-capability-update.tar.gz").read_bytes()
        self.assertEqual(first_bundle, second_bundle)

    def test_manifest_digest_is_mandatory_and_checked(self) -> None:
        with self.assertRaisesRegex(updater.UpdateBarrier, "manifest-sha256-mismatch"):
            updater.inspect_update(str(self.manifest), "0" * 64)
        digest_line = self.digest_file.read_text(encoding="utf-8").strip()
        self.assertTrue(digest_line.startswith(self.manifest_sha + "  "))

    def test_manifest_cannot_escape_aurum_or_install_writable_code(self) -> None:
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["files"][0]["install_path"] = "/etc/cron.d/aurum"
        escaped = self.dist / "escaped.manifest.json"
        escaped.write_text(json.dumps(manifest), encoding="utf-8")
        escaped_sha = hashlib.sha256(escaped.read_bytes()).hexdigest()
        with self.assertRaisesRegex(updater.UpdateBarrier, "outside-aurum-root"):
            updater.inspect_update(str(escaped), escaped_sha)

        manifest["files"][0]["install_path"] = "/opt/aurum/aurum_pi3_console.py"
        manifest["files"][0]["mode"] = "777"
        escaped.write_text(json.dumps(manifest), encoding="utf-8")
        escaped_sha = hashlib.sha256(escaped.read_bytes()).hexdigest()
        with self.assertRaisesRegex(updater.UpdateBarrier, "unsafe-install-mode"):
            updater.inspect_update(str(escaped), escaped_sha)

    def test_apply_requires_confirmation(self) -> None:
        with self.assertRaisesRegex(updater.UpdateBarrier, "explicit-confirmation-required"):
            updater.apply_update(
                str(self.manifest),
                self.manifest_sha,
                confirmed=False,
                install_root=self.root / "card",
                state_dir=self.root / "state",
            )

    def test_apply_is_scoped_atomic_and_backed_up(self) -> None:
        card = self.root / "card"
        target = card / "opt" / "aurum" / "aurum_pi3_console.py"
        target.parent.mkdir(parents=True)
        target.write_text("old console\n", encoding="utf-8")
        result = updater.apply_update(
            str(self.manifest),
            self.manifest_sha,
            confirmed=True,
            install_root=card,
            state_dir=self.root / "state",
        )
        self.assertTrue(result["installed"])
        self.assertIn("AURUM_PI3_READY", target.read_text(encoding="utf-8"))
        self.assertTrue((card / "opt" / "aurum" / "aurum_pi3_update.py").is_file())
        backup = Path(result["backup"]) / "opt" / "aurum" / "aurum_pi3_console.py"
        self.assertEqual(backup.read_text(encoding="utf-8"), "old console\n")
        state = json.loads(
            (self.root / "state" / "last-applied.json").read_text(encoding="utf-8")
        )
        self.assertEqual(state["manifest_sha256"], self.manifest_sha)

    def test_updater_does_not_offer_shell_execution(self) -> None:
        source = (PROJECT / "aurum_pi3_update.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)


if __name__ == "__main__":
    unittest.main()
