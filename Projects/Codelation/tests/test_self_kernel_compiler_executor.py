from __future__ import annotations

import gzip
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kernel_selfbuild.compiler import KernelCompileRequest, compile_commands, compile_kernel
from kernel_selfbuild.external_module import build_external_module
from kernel_selfbuild.module_alias import parse_modules_alias, resolve_modalias
from kernel_selfbuild.seed_inputs import capture_seed_config


class SelfKernelCompilerExecutorTests(unittest.TestCase):
    def _kernel_tree(self, root: Path) -> Path:
        source = root / "linux"
        source.mkdir()
        (source / "Makefile").write_text("VERSION = 0\n", encoding="utf-8")
        (source / "Kconfig").write_text("mainmenu \"test\"\n", encoding="utf-8")
        return source

    def test_x86_compile_command_plan_is_out_of_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._kernel_tree(root)
            config = root / "seed.config"
            config.write_text("CONFIG_MODULES=y\n", encoding="utf-8")
            lsmod = root / "seed.lsmod"
            lsmod.write_text("Module Size Used by\ntest 1 0\n", encoding="utf-8")
            request = KernelCompileRequest("x86_64", source, root / "out", root / "stage", config, jobs=4, lsmod_file=lsmod)
            commands = compile_commands(request)
            flat = [token for command in commands for token in command]
            self.assertIn("ARCH=x86", flat)
            self.assertIn("bzImage", flat)
            self.assertIn("localmodconfig", flat)
            self.assertTrue(any(token.startswith("O=") and str(root / "out") in token for token in flat))
            self.assertFalse(any(token == "install" for token in flat))

    def test_compile_kernel_emits_hashed_manifest_without_host_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._kernel_tree(root)
            config = root / "seed.config"
            config.write_text("CONFIG_MODULES=y\n", encoding="utf-8")
            output = root / "out"
            stage = root / "stage"
            request = KernelCompileRequest("x86_64", source, output, stage, config, jobs=2)
            calls = []

            def fake_runner(command, check=True):
                calls.append(tuple(command))
                if "bzImage" in command:
                    image = output / "arch" / "x86" / "boot" / "bzImage"
                    image.parent.mkdir(parents=True, exist_ok=True)
                    image.write_bytes(b"AURUM TEST KERNEL")
                return subprocess.CompletedProcess(command, 0)

            manifest = compile_kernel(request, runner=fake_runner)
            self.assertEqual(manifest.architecture, "x86_64")
            self.assertEqual(len(manifest.image_sha256), 64)
            self.assertTrue((output / "aurum-kernel-manifest.json").is_file())
            self.assertTrue(all("/boot" not in token for call in calls for token in call))

    def test_compile_command_can_use_content_checked_ccache(self):
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
                compiler_cache="ccache",
            )
            flat = [token for command in compile_commands(request) for token in command]
            self.assertIn("CC=ccache gcc", flat)
            self.assertIn("HOSTCC=ccache gcc", flat)

    def test_external_module_build_never_loads_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kernel = self._kernel_tree(root)
            module = root / "driver"
            module.mkdir()
            (module / "Makefile").write_text("obj-m += aurum_test.o\n", encoding="utf-8")

            def fake_runner(command, check=True):
                (module / "aurum_test.ko").write_bytes(b"fake-ko")
                return subprocess.CompletedProcess(command, 0)

            result = build_external_module(kernel_build_dir=kernel, module_dir=module, runner=fake_runner)
            self.assertFalse(result.loaded)
            self.assertFalse(result.installed_to_running_kernel)
            self.assertEqual(Path(result.ko_files[-1]).name, "aurum_test.ko")

    def test_modalias_resolution_prefers_existing_kernel_module_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            alias_file = Path(tmp) / "modules.alias"
            alias_file.write_text(
                "# test\nalias pci:v00008086d0000* e1000e\nalias usb:v1234p* aurum_usb\n",
                encoding="utf-8",
            )
            aliases = parse_modules_alias(alias_file)
            match = resolve_modalias("pci:v00008086d00001234", aliases)
            self.assertEqual(match.modules, ("e1000e",))

    def test_seed_config_can_be_captured_from_proc_config_gz(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "proc"
            boot = root / "boot"
            proc.mkdir()
            boot.mkdir()
            with gzip.open(proc / "config.gz", "wb") as handle:
                handle.write(b"CONFIG_MODULES=y\n")
            out = root / "seed.config"
            capture_seed_config(out, proc_root=proc, boot_root=boot, kernel_release="test")
            self.assertEqual(out.read_text(encoding="utf-8"), "CONFIG_MODULES=y\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
