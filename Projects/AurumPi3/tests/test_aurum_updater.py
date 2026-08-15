from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_updater.py"
SPEC = importlib.util.spec_from_file_location("aurum_updater", MODULE_PATH)
assert SPEC and SPEC.loader
aurum_updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aurum_updater)


class FakeController:
    def __init__(self) -> None:
        self.scheduled = 0
        self.restarts = 0
        self.fail_release: str | None = None

    def schedule_apply(self) -> None:
        self.scheduled += 1

    def restart_runtime(self) -> None:
        self.restarts += 1

    def wait_ready(self, release_id: str, timeout: float = 45.0) -> tuple[bool, str]:
        if release_id == self.fail_release:
            return False, "injected-readiness-failure"
        return True, "selftest=ok service=active"


class AurumUpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.base = self.root / "opt" / "aurum"
        self.state = self.root / "state"
        self.releases = self.base / "releases"
        self.releases.mkdir(parents=True)
        self.old_release = self._make_release("0.01-bootstrap", "0.01")
        self._link_current(self.old_release)
        self.controller = FakeController()
        self.updater = aurum_updater.AurumUpdater(
            base_dir=self.base,
            state_dir=self.state,
            target="raspberry-pi-3",
            architecture="arm64",
            controller=self.controller,
            selftest_runner=lambda _path, _release: (True, "candidate-selftest=ok"),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _link_current(self, release: Path) -> None:
        current = self.base / "current"
        current.unlink(missing_ok=True)
        current.symlink_to(release, target_is_directory=True)

    def _make_release(self, release_id: str, version: str) -> Path:
        release = self.releases / release_id
        (release / "codelation" / "field").mkdir(parents=True)
        (release / "aurum_pi3_console.py").write_text("print('selftest')\n", encoding="utf-8")
        (release / "RELEASE.json").write_text(
            json.dumps(
                {
                    "schema": "aurum-runtime-release-v1",
                    "version": version,
                    "release_id": release_id,
                    "target": "raspberry-pi-3",
                    "architecture": "arm64",
                }
            ),
            encoding="utf-8",
        )
        return release

    def _update_files(
        self,
        *,
        version: str = "0.02",
        release_id: str = "0.02-test",
        target: str = "raspberry-pi-3",
        architecture: str = "arm64",
        corrupt_hash: bool = False,
    ) -> tuple[Path, str]:
        source = self.root / f"source-{release_id}"
        payload = source / "payload"
        (payload / "codelation" / "field").mkdir(parents=True)
        (payload / "aurum_pi3_console.py").write_text("print('selftest')\n", encoding="utf-8")
        (payload / "RELEASE.json").write_text(
            json.dumps(
                {
                    "schema": "aurum-runtime-release-v1",
                    "version": version,
                    "release_id": release_id,
                    "target": target,
                    "architecture": architecture,
                }
            ),
            encoding="utf-8",
        )
        artifact = self.root / f"{release_id}.tar.gz"
        with tarfile.open(artifact, "w:gz") as archive:
            archive.add(payload, arcname="payload")
        artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest = {
            "schema": "aurum-application-update-v1",
            "version": version,
            "release_id": release_id,
            "target": target,
            "architecture": architecture,
            "minimum_updater_version": "1.0.0",
            "artifact": {
                "url": artifact.name,
                "sha256": "0" * 64 if corrupt_hash else artifact_sha,
                "bytes": artifact.stat().st_size,
                "format": "tar.gz",
                "root": "payload",
            },
        }
        manifest_path = self.root / f"{release_id}.manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        return manifest_path, manifest_sha

    def test_successful_staged_update_activates_only_after_health_check(self) -> None:
        manifest, pin = self._update_files()
        check = self.updater.check(str(manifest), pin)
        self.assertTrue(check["update_available"])
        staged = self.updater.stage(str(manifest), pin)
        self.assertEqual(staged["status"], "staged")
        self.assertEqual((self.base / "current").resolve(), self.old_release.resolve())

        activated = self.updater.apply_pending()
        self.assertEqual(activated["release"], "0.02-test")
        self.assertEqual((self.base / "current").resolve().name, "0.02-test")
        status = self.updater.status()
        self.assertEqual(status["active_release"], "0.02-test")
        self.assertEqual(status["previous_release"], "0.01-bootstrap")
        self.assertIsNone(status["pending"])

    def test_corrupt_artifact_never_activates(self) -> None:
        manifest, pin = self._update_files(corrupt_hash=True)
        with self.assertRaisesRegex(aurum_updater.UpdateError, "Artifact SHA-256 mismatch"):
            self.updater.stage(str(manifest), pin)
        self.assertEqual((self.base / "current").resolve(), self.old_release.resolve())
        self.assertIsNone(self.updater.status()["pending"])

    def test_wrong_target_manifest_is_rejected_before_download(self) -> None:
        manifest, pin = self._update_files(target="aurum-pc")
        with self.assertRaisesRegex(aurum_updater.UpdateError, "expected 'raspberry-pi-3'"):
            self.updater.check(str(manifest), pin)
        self.assertEqual((self.base / "current").resolve(), self.old_release.resolve())

    def test_interrupted_activation_recovers_previous_release(self) -> None:
        manifest, pin = self._update_files()
        staged = self.updater.stage(str(manifest), pin)
        self.updater._activate(staged["candidate_release"])
        state = json.loads(self.updater.state_file.read_text(encoding="utf-8"))
        state["pending"]["phase"] = "health-check"
        aurum_updater._atomic_json(self.updater.state_file, state)

        recovered = self.updater.recover()
        self.assertEqual(recovered["status"], "recovered")
        self.assertEqual((self.base / "current").resolve(), self.old_release.resolve())
        self.assertIsNone(self.updater.status()["pending"])

    def test_failed_readiness_automatically_rolls_back(self) -> None:
        manifest, pin = self._update_files()
        self.updater.stage(str(manifest), pin)
        self.controller.fail_release = "0.02-test"
        with self.assertRaisesRegex(aurum_updater.UpdateError, "injected-readiness-failure"):
            self.updater.apply_pending()
        self.assertEqual((self.base / "current").resolve(), self.old_release.resolve())
        self.assertEqual(self.updater.status()["active_release"], "0.01-bootstrap")

    def test_explicit_rollback_returns_to_previous_healthy_release(self) -> None:
        manifest, pin = self._update_files()
        self.updater.stage(str(manifest), pin)
        self.updater.apply_pending()
        rollback = self.updater.schedule_rollback()
        self.assertEqual(rollback["operation"], "rollback")
        self.updater.apply_pending()
        self.assertEqual((self.base / "current").resolve(), self.old_release.resolve())
        self.assertEqual(self.updater.status()["previous_release"], "0.02-test")

    def test_network_manifest_requires_explicit_authorization(self) -> None:
        with self.assertRaisesRegex(aurum_updater.UpdateError, "explicit authorization"):
            self.updater.check("https://example.invalid/manifest.json", "0" * 64)


if __name__ == "__main__":
    unittest.main()
