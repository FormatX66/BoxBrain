from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "driver_candidates" / "kernel_shadow"))
from verify_kernel_shadow import ContractError, PASS_STATE, canonical_sha256, validate_candidate

REPO = Path(__file__).resolve().parents[3]
CANDIDATE = REPO / "Projects" / "AdaptiveKernel" / "driver_candidates" / "kernel_shadow"
BASIS_RECEIPT = REPO / "Projects" / "AdaptiveKernel" / "results" / "pi3-source-package-provenance-latest.json"
SEMANTIC = REPO / "Projects" / "AdaptiveKernel" / "driver_candidates" / "generated" / "pi3-smsc95xx-nonbinding-candidate.c"


class KernelShadowContractTests(unittest.TestCase):
    def test_real_candidate_is_inert_and_provenance_bound(self):
        receipt = validate_candidate(CANDIDATE, REPO)
        self.assertEqual(receipt["state"], PASS_STATE)
        self.assertTrue(all(value is False for value in receipt["invariants"].values()))
        self.assertEqual(receipt["basis"]["source_package_receipt_sha256"],
                         "04c065a6ff3a98c4d70b6bbfab3d442887a8314ca075662e3d83391456fbfc42")

    def stage(self) -> tuple[tempfile.TemporaryDirectory, Path, Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        candidate = root / "Projects" / "AdaptiveKernel" / "driver_candidates" / "kernel_shadow"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(CANDIDATE, candidate)
        receipt = root / "Projects" / "AdaptiveKernel" / "results" / BASIS_RECEIPT.name
        receipt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASIS_RECEIPT, receipt)
        semantic = root / "Projects" / "AdaptiveKernel" / "driver_candidates" / "generated" / SEMANTIC.name
        semantic.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SEMANTIC, semantic)
        return temp, candidate, root

    def test_hardware_io_capability_is_refused(self):
        temp, candidate, root = self.stage()
        self.addCleanup(temp.cleanup)
        source = candidate / "aurum_pi3_smsc95xx_kernel_shadow.c"
        source.write_text(source.read_text() + "\nstatic void bad(void) { usb_submit_urb((void *)0, 0); }\n")
        with self.assertRaisesRegex(ContractError, "USB URB submission"):
            validate_candidate(candidate, root)

    def test_driver_registration_shape_is_refused(self):
        temp, candidate, root = self.stage()
        self.addCleanup(temp.cleanup)
        source = candidate / "aurum_pi3_smsc95xx_kernel_shadow.c"
        source.write_text(source.read_text() + "\nstatic struct usb_driver bad_driver;\n")
        with self.assertRaisesRegex(ContractError, "USB driver declaration"):
            validate_candidate(candidate, root)

    def test_successful_init_is_refused(self):
        temp, candidate, root = self.stage()
        self.addCleanup(temp.cleanup)
        source = candidate / "aurum_pi3_smsc95xx_kernel_shadow.c"
        source.write_text(source.read_text().replace("return -EPERM;", "return 0;", 1))
        with self.assertRaisesRegex(ContractError, "hard -EPERM"):
            validate_candidate(candidate, root)

    def test_kbuild_extra_object_is_refused(self):
        temp, candidate, root = self.stage()
        self.addCleanup(temp.cleanup)
        (candidate / "Kbuild").write_text("obj-m := aurum_pi3_smsc95xx_kernel_shadow.o bad.o\n")
        with self.assertRaisesRegex(ContractError, "Kbuild may only"):
            validate_candidate(candidate, root)

    def test_semantic_basis_drift_is_refused(self):
        temp, candidate, root = self.stage()
        self.addCleanup(temp.cleanup)
        semantic = root / "Projects" / "AdaptiveKernel" / "driver_candidates" / "generated" / SEMANTIC.name
        semantic.write_bytes(semantic.read_bytes() + b"\n/* drift */\n")
        with self.assertRaisesRegex(ContractError, "semantic shadow basis moved"):
            validate_candidate(candidate, root)

    def test_provenance_authority_regression_is_refused_even_with_valid_seal(self):
        temp, candidate, root = self.stage()
        self.addCleanup(temp.cleanup)
        receipt_path = root / "Projects" / "AdaptiveKernel" / "results" / BASIS_RECEIPT.name
        receipt = json.loads(receipt_path.read_text())
        receipt["authority"]["write_authority"] = True
        receipt.pop("receipt_sha256")
        new_sha = canonical_sha256(receipt)
        receipt["receipt_sha256"] = new_sha
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        manifest_path = candidate / "candidate.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["basis"]["source_package_receipt_sha256"] = new_sha
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        with self.assertRaisesRegex(ContractError, "zero-authority"):
            validate_candidate(candidate, root)

    def test_manifest_cannot_enable_load(self):
        temp, candidate, root = self.stage()
        self.addCleanup(temp.cleanup)
        manifest_path = candidate / "candidate.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["safety"]["load_allowed"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        with self.assertRaisesRegex(ContractError, "load_allowed"):
            validate_candidate(candidate, root)


if __name__ == "__main__":
    unittest.main()
