from __future__ import annotations

import unittest
from pathlib import Path


BUILD_SCRIPT = Path(__file__).parents[1] / "build-iso.sh"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
QEMU_SMOKE = REPOSITORY_ROOT / "Projects" / "AurumVirtualLab" / "qemu-pc-smoke.sh"
PC_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "aurum-pc-v001.yml"


class BuildIsoContractTests(unittest.TestCase):
    def test_boot_requests_only_the_aurum_persistence_volume(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn(" persistence ", script)
        self.assertIn("persistence-label=AURUM_PERSIST", script)
        self.assertIn("preempt=voluntary", script)
        self.assertIn("transparent_hugepage=madvise", script)

    def test_qemu_runtime_gate_requires_on_machine_self_build(self) -> None:
        smoke = QEMU_SMOKE.read_text(encoding="utf-8")
        workflow = PC_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("printf 'self-build\\n'", smoke)
        self.assertIn("AURUM_SELF_BUILD_FINISHED status=passed", smoke)
        self.assertIn("timeout 900s qemu-system-x86_64", smoke)
        self.assertIn("for _ in $(seq 1 720)", smoke)
        self.assertIn("AURUM_VIRTUAL_PC_UEFI_RUNTIME_SELF_BUILD_OK", smoke)
        self.assertIn("Projects/AurumVirtualLab/qemu-pc-smoke.sh", workflow)


if __name__ == "__main__":
    unittest.main()
