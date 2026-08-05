from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]


class MorrisVncTests(unittest.TestCase):
    def test_target_proxy_is_loopback_only(self) -> None:
        start = (ROOT / "scripts" / "start-console.sh").read_text(
            encoding="utf-8"
        )
        stop = (ROOT / "scripts" / "stop-console.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn('"127.0.0.1:$target_websocket_port"', start)
        self.assertIn('"$target_address:$target_port"', start)
        self.assertIn("BOXBRAIN_TARGET_CONSOLE_READY", start)
        self.assertIn("boxbrain-console-target-websocket.service", stop)

    def test_windows_install_is_pinned_and_pi_only(self) -> None:
        install = (
            REPOSITORY_ROOT / "installer" / "install-morris-vnc.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("tightvnc-2.8.88-gpl-setup-64bit.msi", install)
        self.assertIn(
            "fa86d817ac29c5ffe1e8e7095e738d9b", install
        )
        self.assertIn("Get-AuthenticodeSignature", install)
        self.assertIn("O=OOO GlavSoft", install)
        self.assertIn("SERVER_ADD_FIREWALL_EXCEPTION=0", install)
        self.assertIn("-RemoteAddress $PiAddress", install)
        self.assertIn("-LocalAddress $TargetAddress", install)
        self.assertIn("-LocalPort 5900", install)

    def test_launcher_uses_pinned_ssh_loopback_tunnel(self) -> None:
        launcher = (
            REPOSITORY_ROOT / "installer" / "open-morris-console.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("StrictHostKeyChecking=yes", launcher)
        self.assertIn("ExitOnForwardFailure=yes", launcher)
        self.assertIn("127.0.0.1:${RemoteWebSocketPort}", launcher)
        self.assertIn('"nc -zw2 $TargetAddress 5900"', launcher)
        self.assertIn("morris-vnc.clixml", launcher)
        self.assertNotIn("StrictHostKeyChecking=no", launcher)

    def test_shortcut_uses_the_guarded_launcher(self) -> None:
        shortcut = (
            REPOSITORY_ROOT
            / "installer"
            / "install-morris-console-shortcut.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("open-morris-console.ps1", shortcut)
        self.assertIn("Morris PC Remote.lnk", shortcut)
        self.assertIn("Existing Morris PC Remote shortcut preserved", shortcut)


if __name__ == "__main__":
    unittest.main()
