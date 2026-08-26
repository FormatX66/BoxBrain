from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CANDIDATE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CANDIDATE_ROOT))

from compile_only import (
    CompileRefusal,
    build_command,
    compile_candidate,
    inspect_module_artifact,
    validate_kernel_build,
)
from verify_contract import ContractError, validate_candidate


RELEASE = "6.18.34+rpt-rpi-v8"


class DriverCandidateContractTests(unittest.TestCase):
    def fixture_candidate(self, root: Path) -> Path:
        target = root / "candidate"
        shutil.copytree(CANDIDATE_ROOT, target, ignore=shutil.ignore_patterns("tests", "__pycache__"))
        return target

    def fixture_headers(self, root: Path, release: str = RELEASE) -> Path:
        headers = root / "headers"
        (headers / "include" / "config").mkdir(parents=True)
        (headers / "Makefile").write_text("VERSION = 6\n", encoding="utf-8")
        (headers / ".config").write_text("CONFIG_ARM64=y\nCONFIG_MODULES=y\n", encoding="utf-8")
        (headers / "Module.symvers").write_text("fixture-symbols\n", encoding="utf-8")
        (headers / "include" / "config" / "kernel.release").write_text(release + "\n", encoding="utf-8")
        return headers

    def test_repository_candidate_is_verified_inert_and_compile_only(self):
        receipt = validate_candidate()
        self.assertEqual(receipt["state"], "verified-inert-compile-only")
        self.assertEqual(receipt["target_model_marker"], "Raspberry Pi 3 Model B Rev 1.2")
        self.assertFalse(receipt["invariants"]["load_allowed"])
        self.assertFalse(receipt["invariants"]["successful_load_possible"])
        self.assertFalse(receipt["invariants"]["autoload_possible"])
        self.assertFalse(receipt["invariants"]["driver_registration_present"])
        self.assertFalse(receipt["invariants"]["firmware_boot_network_mutation_present"])

    def test_same_family_wrong_model_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = self.fixture_candidate(Path(directory))
            manifest_path = candidate / "candidate.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["target"]["model_marker"] = "Raspberry Pi 3 Model B Rev 1.3"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ContractError):
                validate_candidate(candidate)

    def test_alias_driver_registration_and_self_load_are_rejected(self):
        mutations = (
            'MODULE_ALIAS("usb:v0424pEC00*");',
            "module_usb_driver(aurum_usb_driver);",
            'request_module("smsc95xx");',
            "symbol_get(register_netdev);",
            "register_netdev(dev);",
            'request_firmware(&fw, "candidate.bin", dev);',
            "usb_submit_urb(urb, GFP_KERNEL);",
            "sysfs_create_file(kobj, attr);",
            'kernel_restart("candidate");',
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                candidate = self.fixture_candidate(Path(directory))
                source = candidate / "aurum_pi3_compile_probe.c"
                source.write_text(source.read_text(encoding="utf-8") + "\n" + mutation + "\n", encoding="utf-8")
                with self.assertRaises(ContractError):
                    validate_candidate(candidate)

    def test_init_must_remain_an_unconditional_load_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = self.fixture_candidate(Path(directory))
            source = candidate / "aurum_pi3_compile_probe.c"
            text = source.read_text(encoding="utf-8").replace("return -EPERM;", "return 0;")
            source.write_text(text, encoding="utf-8")
            with self.assertRaises(ContractError):
                validate_candidate(candidate)

    def test_kbuild_cannot_gain_an_install_target(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = self.fixture_candidate(Path(directory))
            with (candidate / "Kbuild").open("a", encoding="utf-8") as stream:
                stream.write("modules_install:\n\t@false\n")
            with self.assertRaises(ContractError):
                validate_candidate(candidate)

    def test_header_tree_requires_exact_release_and_arm64_config(self):
        with tempfile.TemporaryDirectory() as directory:
            headers = self.fixture_headers(Path(directory), release="different-kernel")
            with self.assertRaises(CompileRefusal):
                validate_kernel_build(headers, RELEASE)
            (headers / "include" / "config" / "kernel.release").write_text(RELEASE + "\n", encoding="utf-8")
            (headers / ".config").write_text("CONFIG_X86_64=y\n", encoding="utf-8")
            with self.assertRaises(CompileRefusal):
                validate_kernel_build(headers, RELEASE)

    def test_compile_runner_uses_only_modules_target_and_discards_artifact(self):
        calls = []

        def fake_runner(command, **kwargs):
            calls.append((command, kwargs))
            tool = Path(command[0]).name
            if tool == "make":
                module_root = Path(next(item[2:] for item in command if item.startswith("M=")))
                (module_root / "aurum_pi3_compile_probe.ko").write_bytes(
                    b"fixture-vermagic:" + RELEASE.encode("utf-8")
                )
                output = "fixture compile passed\n"
            elif tool == "modinfo" and command[2] == "vermagic":
                output = f"{RELEASE} SMP preempt mod_unload modversions aarch64\n"
            elif tool == "modinfo" and command[2] == "alias":
                output = ""
            elif tool.endswith("nm") and "--undefined-only" in command:
                output = "__fentry__ U\n"
            elif tool.endswith("nm"):
                output = "aurum_pi3_compile_probe_init t 0 4\n"
            else:
                raise AssertionError(f"unexpected tool call: {command}")
            return subprocess.CompletedProcess(command, 0, stdout=output)

        def tool_resolver(name):
            if name == "modinfo":
                return "/tools/modinfo"
            if name == "aarch64-linux-gnu-nm":
                return "/tools/aarch64-linux-gnu-nm"
            return None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            headers = self.fixture_headers(root)
            receipt_path = root / "receipt.json"
            receipt = compile_candidate(
                kernel_build=headers,
                expected_release=RELEASE,
                receipt_path=receipt_path,
                cross_compile="aarch64-linux-gnu-",
                runner=fake_runner,
                tool_resolver=tool_resolver,
            )
            self.assertEqual(receipt["state"], "verified-compile-only")
            self.assertTrue(receipt["build"]["temporary_build_removed"])
            self.assertTrue(receipt["build"]["artifact_inspection_recorded_before_artifact_removal"])
            self.assertFalse(receipt["build"]["artifact_retained"])
            self.assertFalse(receipt["build"]["loader_invoked"])
            self.assertFalse(receipt["build"]["installer_invoked"])
            self.assertEqual(receipt["artifact_inspection"]["state"], "verified-inert-artifact")
            self.assertTrue(receipt["artifact_inspection"]["exact_vermagic"])
            self.assertEqual(receipt["artifact_inspection"]["aliases"], [])
            self.assertEqual(receipt["artifact_inspection"]["device_table_symbols"], [])
            self.assertEqual(receipt["artifact_inspection"]["forbidden_unresolved_symbols"], [])
            self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8"))["state"], "verified-compile-only")

        self.assertEqual(len(calls), 5)
        command = calls[0][0]
        self.assertEqual(command[-2:], ["ARCH=arm64", "modules"])
        self.assertNotIn("modules_install", command)
        self.assertNotIn("install", command)
        self.assertNotIn("insmod", command)
        self.assertNotIn("modprobe", command)

    def test_artifact_inspection_rejects_vermagic_alias_table_and_capability_symbol(self):
        def inspect_with(*, vermagic=RELEASE, aliases="", symbols="", unresolved="__fentry__ U\n"):
            def runner(command, **kwargs):
                tool = Path(command[0]).name
                if tool == "modinfo" and command[2] == "vermagic":
                    output = vermagic + " SMP aarch64\n"
                elif tool == "modinfo" and command[2] == "alias":
                    output = aliases
                elif tool == "nm" and "--undefined-only" in command:
                    output = unresolved
                elif tool == "nm":
                    output = symbols
                else:
                    raise AssertionError(command)
                return subprocess.CompletedProcess(command, 0, stdout=output)

            with tempfile.TemporaryDirectory() as directory:
                module = Path(directory) / "candidate.ko"
                module.write_bytes(b"fixture")
                return inspect_module_artifact(
                    module,
                    RELEASE,
                    runner=runner,
                    tool_resolver=lambda name: name if name in {"modinfo", "nm"} else None,
                )

        cases = (
            ({"vermagic": "6.18.33+rpt-rpi-v8"}, "failed-exact-vermagic"),
            ({"aliases": "usb:v0424pEC00*\n"}, "failed-module-alias-present"),
            ({"symbols": "__mod_usb__fixture_device_table D 0 8\n"}, "failed-device-table-present"),
            ({"unresolved": "register_netdev U\n"}, "failed-forbidden-unresolved-symbol"),
        )
        for inputs, expected_state in cases:
            with self.subTest(expected_state=expected_state):
                self.assertEqual(inspect_with(**inputs)["state"], expected_state)

    def test_missing_inspection_tools_hold_instead_of_claiming_success(self):
        with tempfile.TemporaryDirectory() as directory:
            module = Path(directory) / "candidate.ko"
            module.write_bytes(b"fixture")
            receipt = inspect_module_artifact(
                module,
                RELEASE,
                tool_resolver=lambda _name: None,
                tools_required=False,
            )
        self.assertEqual(receipt["state"], "held-artifact-inspection-tools-unavailable")
        self.assertEqual(receipt["missing_tools"], ["modinfo", "nm"])

    def test_artifact_symbol_and_tool_outputs_are_bounded(self):
        unresolved = "".join(f"safe_symbol_{index} U\n" for index in range(200))

        def runner(command, **kwargs):
            tool = Path(command[0]).name
            if tool == "modinfo" and command[2] == "vermagic":
                output = RELEASE + " SMP aarch64\n"
            elif tool == "modinfo":
                output = ""
            elif "--undefined-only" in command:
                output = unresolved
            else:
                output = "aurum_pi3_compile_probe_init t 0 4\n"
            return subprocess.CompletedProcess(command, 0, stdout=output)

        with tempfile.TemporaryDirectory() as directory:
            module = Path(directory) / "candidate.ko"
            module.write_bytes(b"fixture")
            receipt = inspect_module_artifact(
                module,
                RELEASE,
                runner=runner,
                tool_resolver=lambda name: name if name in {"modinfo", "nm"} else None,
            )
        self.assertEqual(receipt["state"], "verified-inert-artifact")
        self.assertEqual(receipt["unresolved_symbol_count"], 200)
        self.assertEqual(len(receipt["unresolved_symbols"]), 128)
        self.assertTrue(receipt["unresolved_symbols_truncated"])
        self.assertTrue(all(len(run["output"]) <= 4000 for run in receipt["tool_runs"]))

    def test_build_command_has_no_load_install_or_clean_side_effect(self):
        command = build_command(Path("/headers"), Path("/candidate"))
        self.assertEqual(command[0], "make")
        self.assertEqual(command[-1], "modules")
        self.assertTrue(any(item.startswith("M=") for item in command))
        for forbidden in ("install", "modules_install", "insmod", "modprobe", "depmod", "clean"):
            self.assertNotIn(forbidden, command)


if __name__ == "__main__":
    unittest.main()
