from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kernel_selfbuild.compiler import (  # noqa: E402
    KernelCompileRequest,
    compile_commands,
    compile_kernel,
)


class SelfKernelCompilerExecutorTests(unittest.TestCase):
    def _kernel_tree(self, root: Path) -> Path:
        source = root / "linux"
        source.mkdir()
        (source / "Makefile").write_text(
            "VERSION = 7\n"
            "PATCHLEVEL = 0\n"
            "SUBLEVEL = 1\n"
            "EXTRAVERSION = -aurum-test\n",
            encoding="utf-8",
        )
        (source / "Kconfig").write_text('mainmenu "test"\n', encoding="utf-8")
        scripts = source / "scripts"
        scripts.mkdir()
        (scripts / "setlocalversion").write_text("test\n", encoding="utf-8")
        return source

    def test_boot_profile_builds_image_without_modules_or_host_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._kernel_tree(root)
            config = root / "seed.config"
            config.write_text("CONFIG_MODULES=y\n", encoding="utf-8")
            request = KernelCompileRequest(
                "x86_64",
                source,
                root / "out",
                root / "stage",
                config,
                jobs=4,
                build_modules=False,
            )

            commands = compile_commands(request)
            flat = [token for command in commands for token in command]

            self.assertIn("ARCH=x86", flat)
            self.assertIn("bzImage", flat)
            self.assertNotIn("modules", flat)
            self.assertNotIn("modules_install", flat)
            self.assertNotIn("install", flat)

    def test_machine_profile_can_build_and_stage_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._kernel_tree(root)
            config = root / "seed.config"
            config.write_text("CONFIG_MODULES=y\n", encoding="utf-8")
            request = KernelCompileRequest(
                "x86_64",
                source,
                root / "out",
                root / "stage",
                config,
                build_modules=True,
            )

            flat = [token for command in compile_commands(request) for token in command]

            self.assertIn("modules", flat)
            self.assertIn("modules_install", flat)
            self.assertTrue(any(token.startswith("INSTALL_MOD_PATH=") for token in flat))

    def test_arm64_profile_can_record_device_tree_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._kernel_tree(root)
            config = root / "seed.config"
            config.write_text("CONFIG_MODULES=y\n", encoding="utf-8")
            request = KernelCompileRequest(
                "arm64",
                source,
                root / "out",
                root / "stage",
                config,
                jobs=8,
                build_modules=True,
                extra_build_targets=("dtbs",),
                cross_compile="aarch64-linux-gnu-",
            )

            commands = compile_commands(request)
            flat = [token for command in commands for token in command]

            self.assertIn("ARCH=arm64", flat)
            self.assertIn("CROSS_COMPILE=aarch64-linux-gnu-", flat)
            self.assertIn("Image", flat)
            self.assertIn("dtbs", flat)
            self.assertIn("modules", flat)
            self.assertLess(flat.index("dtbs"), flat.index("modules"))

    def test_extra_build_targets_reject_make_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._kernel_tree(root)
            config = root / "seed.config"
            config.write_text("CONFIG_MODULES=y\n", encoding="utf-8")
            request = KernelCompileRequest(
                "arm64",
                source,
                root / "out",
                root / "stage",
                config,
                extra_build_targets=("--eval=unsafe",),
            )

            with self.assertRaisesRegex(ValueError, "invalid make target"):
                compile_commands(request)

    def test_compile_emits_hashed_versioned_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._kernel_tree(root)
            config = root / "seed.config"
            config.write_text("CONFIG_MODULES=y\n", encoding="utf-8")
            output = root / "out"
            request = KernelCompileRequest(
                "x86_64",
                source,
                output,
                root / "stage",
                config,
                jobs=2,
            )
            calls = []

            def fake_runner(command, check=True):
                calls.append(tuple(command))
                if "bzImage" in command:
                    image = output / "arch" / "x86" / "boot" / "bzImage"
                    image.parent.mkdir(parents=True, exist_ok=True)
                    image.write_bytes(b"AURUM TEST KERNEL")
                return subprocess.CompletedProcess(command, 0)

            manifest = compile_kernel(request, runner=fake_runner)
            payload = json.loads(
                (output / "aurum-kernel-manifest.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest.schema, "aurum-machine-kernel-artifact-v1")
            self.assertEqual(manifest.kernel_version, "7.0.1-aurum-test")
            self.assertEqual(len(manifest.image_sha256), 64)
            self.assertEqual(len(manifest.source_identity), 64)
            self.assertFalse(payload["build_modules"])
            self.assertTrue(calls)

    def test_output_must_not_be_inside_source_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._kernel_tree(root)
            config = root / "seed.config"
            config.write_text("CONFIG_MODULES=y\n", encoding="utf-8")
            request = KernelCompileRequest(
                "x86_64",
                source,
                source / "out",
                root / "stage",
                config,
            )

            with self.assertRaisesRegex(ValueError, "must not be inside"):
                compile_commands(request)


if __name__ == "__main__":
    unittest.main(verbosity=2)
