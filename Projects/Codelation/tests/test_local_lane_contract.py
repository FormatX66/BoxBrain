from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
WATCHER = ROOT / "installer" / "aurum-local-lane" / "watch-aurum-local-lane.ps1"
DEPLOYER = ROOT / "installer" / "deploy-aurum-live-to-pi.ps1"


class LocalLaneContractTests(unittest.TestCase):
    def test_deployer_keeps_bounded_bbpi4_fallback_routes(self):
        text = DEPLOYER.read_text(encoding="utf-8")
        for address in ("10.42.194.1", "10.12.194.1", "192.168.0.194"):
            self.assertIn(address, text)
        self.assertIn("foreach ($address in $PiAddresses)", text)

    def test_watcher_does_not_force_the_lan_only_route(self):
        text = WATCHER.read_text(encoding="utf-8")
        self.assertNotIn('-PiAddresses "192.168.0.194"', text)
        self.assertIn("-File $deployer -KeyPath", text)

    def test_verification_probes_the_same_approved_route_set(self):
        text = WATCHER.read_text(encoding="utf-8")
        self.assertIn(
            '$addresses = @("10.42.194.1", "10.12.194.1", "192.168.0.194")',
            text,
        )
        self.assertIn("foreach ($address in $addresses)", text)
        self.assertIn("Address = $address; Text = $text", text)


if __name__ == "__main__":
    unittest.main()
