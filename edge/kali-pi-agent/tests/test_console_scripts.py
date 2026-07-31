from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]


class PiConsoleScriptTests(unittest.TestCase):
    def test_default_install_does_not_enable_console(self) -> None:
        default_install = (ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

        self.assertEqual(version, "0.11.0")
        self.assertNotIn("install-console.sh", default_install)
        self.assertNotIn("boxbrain-console-start", default_install)
        self.assertNotIn("boxbrain-console-display", default_install)

    def test_console_installer_pins_and_verifies_novnc(self) -> None:
        installer = (ROOT / "scripts" / "install-console.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("novnc_version=1.7.0", installer)
        self.assertIn(
            "b1003a11b6e6e8d8f7f5e5586daae7f8ca651d8aee0aa155ff9ac841c48f52c6",
            installer,
        )
        self.assertIn("--proto '=https'", installer)
        self.assertIn("sha256sum -c -", installer)
        self.assertIn("LICENSE.txt", installer)
        self.assertIn("license=MPL-2.0", installer)
        self.assertNotIn("apt-get", installer)
        self.assertNotIn("systemctl enable", installer)

    def test_console_transport_is_loopback_and_opt_in(self) -> None:
        start = (ROOT / "scripts" / "start-console.sh").read_text(
            encoding="utf-8"
        )
        stop = (ROOT / "scripts" / "stop-console.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("-localhost", start)
        self.assertIn("127.0.0.1:6080 127.0.0.1:5901", start)
        self.assertIn("BOXBRAIN_CONSOLE_READY", start)
        self.assertIn("10.12.194.1", start)
        self.assertNotIn("0.0.0.0", start)
        self.assertNotIn("systemctl enable", start)
        self.assertIn("boxbrain-console-display.service", stop)

    def test_windows_launcher_requires_verified_ssh_tunnel(self) -> None:
        launcher = (
            REPOSITORY_ROOT / "installer" / "open-pi-console.ps1"
        ).read_text(encoding="utf-8")
        setup = (
            REPOSITORY_ROOT / "installer" / "setup-pi-console.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("StrictHostKeyChecking=yes", launcher)
        self.assertIn("BatchMode=yes", launcher)
        self.assertIn("ExitOnForwardFailure=yes", launcher)
        self.assertIn("sudo -n /usr/local/bin/boxbrain-console-start", launcher)
        self.assertIn("127.0.0.1:{0}:127.0.0.1:6080", launcher)
        self.assertIn("/current/vnc.html", launcher)
        self.assertIn("host=127.0.0.1", launcher)
        self.assertNotIn("StrictHostKeyChecking=no", launcher)
        self.assertIn("StrictHostKeyChecking=yes", setup)
        self.assertIn("/tmp/boxbrain-console-", setup)
        self.assertIn("sudo -n sh", setup)
        self.assertNotIn("StrictHostKeyChecking=no", setup)

    def test_posix_scripts_parse(self) -> None:
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("A POSIX shell is not available.")

        for name in (
            "configure-drive.sh",
            "install-console.sh",
            "start-console.sh",
            "stop-console.sh",
        ):
            completed = subprocess.run(
                [shell, "-n", str(ROOT / "scripts" / name)],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_drive_enrollment_is_explicit_and_does_not_install_dependencies(self) -> None:
        configure = (ROOT / "scripts" / "configure-drive.sh").read_text(
            encoding="utf-8"
        )
        install = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

        self.assertIn("CONFIGURE DRIVE", configure)
        self.assertIn("CONNECT $expected_email", configure)
        self.assertIn("root_folder_id", configure)
        self.assertIn("scope", configure)
        self.assertIn("boxbrain-drive-sync.timer", configure)
        self.assertIn('rclone config create "$remote" drive', configure)
        self.assertIn("scope=drive", configure)
        self.assertIn('root_folder_id="$root_folder_id"', configure)
        self.assertIn("config_is_local=true", configure)
        self.assertIn("--no-output", configure)
        self.assertIn("configparser.ConfigParser", configure)
        self.assertIn("systemctl start --no-block boxbrain-drive-sync.service", configure)
        self.assertNotIn("rclone config redacted", configure)
        self.assertNotIn("apt-get", configure)
        self.assertNotIn("curl", configure)

        service = (ROOT / "systemd" / "boxbrain-drive-sync.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("TimeoutStartSec=1h", service)
        self.assertNotIn("enable boxbrain-drive-sync.timer", install)


if __name__ == "__main__":
    unittest.main()
