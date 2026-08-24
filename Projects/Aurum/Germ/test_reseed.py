#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import bridge
import reseed


class ReseedGermTests(unittest.TestCase):
    def test_repository_manifest_is_compatible(self) -> None:
        manifest = reseed.load_manifest(Path(__file__).with_name("GENETICS.json"))
        self.assertEqual(manifest["schema"], reseed.SCHEMA)
        self.assertEqual(manifest["repository"], reseed.REPOSITORY)
        self.assertTrue(manifest["policy"]["candidate_only_staging"])
        self.assertFalse(manifest["policy"]["live_overwrite_allowed"])
        self.assertTrue(manifest["policy"]["promotion_requires_health_evidence"])
        self.assertIn("x86_64", manifest["platforms"])
        self.assertIn("arm64", manifest["platforms"])
        for name in (
            "recovery_ledger.py",
            "proof.py",
            "rollback_drill.py",
            "recovery_control.py",
            "recovery_poller.py",
            "triage.py",
        ):
            self.assertIn(name, bridge.GERM_FILES)
            self.assertIn(f"Projects/Aurum/Germ/{name}", manifest["required_paths"])

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
                        "platforms": {"x86_64": {}},
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

    def test_invalid_ref_is_refused(self) -> None:
        for ref in ("--upload-pack=evil", "../main", "main//bad", "refs/heads/x.lock"):
            with self.subTest(ref=ref):
                with self.assertRaises(reseed.GermError):
                    reseed.validate_ref(ref)

    def test_stage_requires_explicit_network_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(reseed.GermError):
                reseed.stage(ref="main", state_root=Path(td), authorize_network=False)

    def test_plan_preserves_lkg_until_postboot_health(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            payload = reseed.plan("main", Path(td))
            self.assertFalse(payload["live_overwrite"])
            self.assertTrue(payload["lkg_preserved_until_postboot_health"])
            self.assertEqual(payload["flow"][-1], "promote-or-rollback")

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

    def test_legacy_console_patch_is_bounded_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            console = Path(td) / "aurum_console.py"
            console.write_text(
                "import json\n"
                "from aurum_workspace import AurumWorkspace, WorkspaceError\n"
                "def command_help():\n"
                "    print(\n"
                "        \"install confirm ERASE-CODE | reboot | poweroff | help\",\n"
                "    )\n"
                "def main():\n"
                "    while True:\n"
                "        tokens=[]\n"
                "        command='x'\n"
                "        elif_marker = False\n"
                "        elif command == \"reboot\" and len(tokens) == 1:\n"
                "            pass\n",
                encoding="utf-8",
            )
            first = bridge.patch_console_file(console)
            second = bridge.patch_console_file(console)
            text = console.read_text(encoding="utf-8")
            self.assertEqual(first["status"], "patched")
            self.assertEqual(second["status"], "already-patched")
            self.assertIn("from aurum_germ import handle_reseed", text)
            self.assertIn('command == "reseed"', text)

    def test_bridge_repairs_installed_resolver_and_records_enablement(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            resolved = root / "lib/systemd/system/systemd-resolved.service"
            resolved.parent.mkdir(parents=True)
            resolved.write_text("[Unit]\nDescription=fixture\n", encoding="utf-8")

            repair = bridge._install_units(root)

            resolver = root / "etc/systemd/system/aurum-resolver-link.service"
            self.assertIn(
                "ExecStart=/bin/ln -sfn /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf",
                resolver.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                (root / "etc/NetworkManager/conf.d/10-aurum-resolved.conf").read_text(encoding="utf-8"),
                "[main]\ndns=systemd-resolved\nrc-manager=symlink\n",
            )
            wants = root / "etc/systemd/system/multi-user.target.wants"
            self.assertEqual((wants / resolver.name).readlink(), Path("../aurum-resolver-link.service"))
            self.assertEqual(
                (wants / "systemd-resolved.service").readlink(),
                Path("/lib/systemd/system/systemd-resolved.service"),
            )
            self.assertTrue(repair["resolver_link_unit_installed"])
            self.assertTrue(repair["systemd_resolved_available"])
            self.assertTrue(repair["systemd_resolved_enabled"])
            self.assertTrue(repair["boot_proof_enabled"])
            self.assertTrue(repair["recovery_poll_timer_enabled"])
            self.assertTrue(repair["triage_unit_installed"])

    def test_bridge_does_not_install_dangling_resolver_without_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repair = bridge._install_units(root)
            systemd = root / "etc/systemd/system"
            wants = systemd / "multi-user.target.wants"
            self.assertFalse((systemd / "aurum-resolver-link.service").exists())
            self.assertFalse((wants / "aurum-resolver-link.service").is_symlink())
            self.assertFalse((wants / "systemd-resolved.service").is_symlink())
            self.assertFalse(repair["resolver_link_unit_installed"])
            self.assertFalse(repair["systemd_resolved_available"])
            self.assertFalse(repair["systemd_resolved_enabled"])

    def test_bridge_installs_recovery_wrappers_and_policy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "target"
            source = Path(td) / "Projects/Aurum/Germ"
            recovery = source.parent / "Recovery"
            recovery.mkdir(parents=True)
            (recovery / "trusted-refs.json").write_text(
                '{"schema":"aurum-recovery-trust-v1","specific_states":[]}\n',
                encoding="utf-8",
            )
            (recovery / "authority-public.pem").write_text("fixture-public-key\n", encoding="utf-8")
            bridge._install_wrapper(root)
            installed = bridge._install_recovery_policy(root, source)

            for name, script in (
                ("aurum-reseed", "reseed.py"),
                ("aurum-rollback-drill", "rollback_drill.py"),
                ("aurum-recovery-poll", "recovery_poller.py"),
                ("aurum-triage", "triage.py"),
            ):
                wrapper = root / "usr/sbin" / name
                self.assertIn(f"/usr/lib/aurum/germ/{script}", wrapper.read_text(encoding="utf-8"))
            self.assertTrue(installed["trust_policy_installed"])
            self.assertTrue(installed["authority_enrolled"])

    def test_candidate_install_preserves_existing_inactive_slot_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slot = root / "slots/B"
            candidate = root / "candidate/B"
            snapshot = root / "slot-snapshots/fixture-B"
            (slot / "opt/aurum").mkdir(parents=True)
            (slot / "opt/aurum/old.txt").write_text("old\n", encoding="utf-8")
            (candidate / "opt/aurum").mkdir(parents=True)
            (candidate / "opt/aurum/new.txt").write_text("new\n", encoding="utf-8")

            reseed._replace_inactive_slot(candidate, slot, snapshot)

            self.assertEqual((snapshot / "opt/aurum/old.txt").read_text(encoding="utf-8"), "old\n")
            self.assertEqual((slot / "opt/aurum/new.txt").read_text(encoding="utf-8"), "new\n")
            self.assertFalse(candidate.exists())


if __name__ == "__main__":
    unittest.main()
