import unittest
from pathlib import Path


class Pi3Smsc95xxCandidateCloudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[3]
        cls.workflow = (
            cls.repo / ".github/workflows/aurum-pi3-smsc95xx-nonbinding-candidate.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_is_cloud_only(self):
        lower = self.workflow.lower()
        self.assertIn("runs-on: ubuntu-24.04", lower)
        self.assertNotIn("169.254.129.122", lower)
        self.assertNotIn("ssh ", lower)
        self.assertNotIn("id_ed25519", lower)
        self.assertNotIn("pi3_known_hosts", lower)

    def test_workflow_cannot_build_or_load_kernel_module(self):
        lower = self.workflow.lower()
        self.assertNotIn("modprobe", lower)
        self.assertNotIn("insmod", lower)
        self.assertNotIn("modules_install", lower)
        self.assertNotIn(".ko", lower)
        self.assertIn("aarch64-linux-gnu-gcc", lower)
        self.assertIn("libc6-dev-arm64-cross", lower)
        self.assertIn("[skip ci]", lower)

    def test_workflow_invokes_package_modules_from_repo_root(self):
        for module in (
            "pi3_smsc95xx_candidate_synth",
            "pi3_smsc95xx_candidate_differential",
            "pi3_smsc95xx_candidate_cloud",
        ):
            self.assertIn(f"python -m Projects.AdaptiveKernel.{module}", self.workflow)
            self.assertNotIn(f"python Projects/AdaptiveKernel/{module}.py", self.workflow)

    def test_workflow_persists_only_from_main(self):
        self.assertIn("if: github.ref == 'refs/heads/main'", self.workflow)


if __name__ == "__main__":
    unittest.main()
