from __future__ import annotations

from base64 import b64decode
import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from boxbrain.headless_link import (
    FIXED_ONBOARDING_URL,
    HEADLESS_LINK_AUTHORIZATION,
    HEADLESS_LINK_CONFIRMATION,
    HeadlessLinkError,
    TextEvent,
    _write_report,
    build_bootstrap_command,
    build_keystroke_plan,
    execute_headless_windows_link,
    preview_headless_windows_link,
    send_keystroke_plan,
)


class HeadlessWindowsLinkTests(unittest.TestCase):
    def test_bootstrap_is_fixed_hash_checked_and_credential_free(self) -> None:
        digest = "a" * 64
        command = build_bootstrap_command(digest)
        encoded = command.rsplit(" ", 1)[1]
        decoded = b64decode(encoded).decode("utf-16-le")

        self.assertIn(FIXED_ONBOARDING_URL, decoded)
        self.assertIn(digest, decoded)
        self.assertIn("Get-FileHash -Algorithm SHA256", decoded)
        self.assertIn("-File $p -Authorized", decoded)
        for forbidden in (
            "key=clear",
            "Key Content",
            "passphrase",
            "password=",
            "EncodedArguments",
        ):
            self.assertNotIn(forbidden, decoded)

    def test_plan_uses_only_fixed_keys_and_generated_command(self) -> None:
        plan = build_keystroke_plan("b" * 64)
        text = "".join(
            event.text for event in plan if isinstance(event, TextEvent)
        )
        self.assertEqual(len(plan), 6)
        self.assertTrue(text.startswith("powershell.exe -NoLogo -NoProfile"))
        self.assertNotIn("CONNECT HEADLESS WINDOWS", text)
        self.assertNotIn("password", text.lower())

    def test_fixed_plan_is_encodable_as_usb_hid_reports(self) -> None:
        plan = build_keystroke_plan("c" * 64)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "hid-reports.bin"
            output.write_bytes(b"")
            send_keystroke_plan(plan, output, sleeper=lambda _: None)
            reports = output.read_bytes()

        self.assertGreater(len(reports), 8)
        self.assertEqual(len(reports) % 8, 0)
        self.assertEqual(reports[-8:], bytes(8))

    def test_hid_report_retries_only_transient_not_ready_error(self) -> None:
        delays: list[float] = []
        with patch(
            "boxbrain.headless_link.os.write",
            side_effect=(
                BlockingIOError(errno.EAGAIN, "temporarily unavailable"),
                8,
            ),
        ) as writer:
            _write_report(
                7,
                0,
                0x04,
                sleeper=delays.append,
                max_attempts=3,
            )

        self.assertEqual(writer.call_count, 2)
        self.assertEqual(len(delays), 1)

    def test_hid_report_stops_after_bounded_not_ready_retries(self) -> None:
        with (
            patch(
                "boxbrain.headless_link.os.write",
                side_effect=BlockingIOError(
                    errno.EAGAIN,
                    "temporarily unavailable",
                ),
            ) as writer,
            self.assertRaisesRegex(HeadlessLinkError, "did not become ready"),
        ):
            _write_report(
                7,
                0,
                0x04,
                sleeper=lambda _: None,
                max_attempts=3,
            )

        self.assertEqual(writer.call_count, 3)

    def test_preview_is_no_change_and_reports_hid_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / "windows-link.ps1"
            device = root / "hidg0"
            helper.write_text("Write-Output 'fixture'\n", encoding="utf-8")
            device.write_bytes(b"")

            result = preview_headless_windows_link(
                script_path=helper,
                hid_device=device,
                effective_uid=1000,
            )

        self.assertEqual(result["action"], "preview")
        self.assertFalse(result["changed"])
        self.assertFalse(result["hid_ready"])
        self.assertFalse(result["running_as_root"])
        self.assertFalse(result["credentials_typed"])

    def test_execute_refuses_before_hid_access_without_exact_approval(self) -> None:
        with self.assertRaisesRegex(HeadlessLinkError, "authorization"):
            execute_headless_windows_link("", HEADLESS_LINK_CONFIRMATION)
        with self.assertRaisesRegex(HeadlessLinkError, "exact confirmation"):
            execute_headless_windows_link(HEADLESS_LINK_AUTHORIZATION, "wrong")

    def test_execute_does_not_type_into_an_already_linked_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "windows-link.ps1"
            helper.write_text("Write-Output 'fixture'\n", encoding="utf-8")
            with (
                patch("boxbrain.headless_link._is_hid_device", return_value=True),
                self.assertRaisesRegex(HeadlessLinkError, "already has"),
            ):
                execute_headless_windows_link(
                    HEADLESS_LINK_AUTHORIZATION,
                    HEADLESS_LINK_CONFIRMATION,
                    script_path=helper,
                    effective_uid=0,
                    sender=lambda *_: self.fail("sender must remain unused"),
                    verifier=lambda *_args, **_kwargs: {
                        "hostname": "ALREADY-LINKED"
                    },
                )

    def test_execute_requires_key_only_ssh_verification(self) -> None:
        captured: list[object] = []

        def sender(plan: object, device: Path) -> None:
            captured.extend((plan, device))

        verification_calls = 0

        def verifier(address: str, **kwargs: object) -> dict[str, object] | None:
            nonlocal verification_calls
            verification_calls += 1
            if verification_calls == 1:
                return None
            return {
                "address": address,
                "hostname": "HEADLESS-TEST",
                "transport": kwargs["transport"],
            }

        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "windows-link.ps1"
            helper.write_text("Write-Output 'fixture'\n", encoding="utf-8")
            with (
                patch("boxbrain.headless_link._is_hid_device", return_value=True),
                patch(
                    "boxbrain.headless_link.save_link",
                    side_effect=lambda link: link,
                ),
            ):
                result = execute_headless_windows_link(
                    HEADLESS_LINK_AUTHORIZATION,
                    HEADLESS_LINK_CONFIRMATION,
                    script_path=helper,
                    effective_uid=0,
                    sender=sender,
                    verifier=verifier,
                    sleeper=lambda _: None,
                )

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["verification"], "key-only SSH succeeded")
        self.assertFalse(result["credentials_typed"])
        self.assertEqual(len(captured), 2)
        self.assertEqual(verification_calls, 2)

    def test_execute_reports_unverified_instead_of_blind_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "windows-link.ps1"
            helper.write_text("Write-Output 'fixture'\n", encoding="utf-8")
            with (
                patch("boxbrain.headless_link._is_hid_device", return_value=True),
                patch(
                    "boxbrain.headless_link.time.monotonic",
                    side_effect=(0.0, 0.0, 2.0),
                ),
                self.assertRaisesRegex(HeadlessLinkError, "Do not assume"),
            ):
                execute_headless_windows_link(
                    HEADLESS_LINK_AUTHORIZATION,
                    HEADLESS_LINK_CONFIRMATION,
                    script_path=helper,
                    effective_uid=0,
                    sender=lambda *_: None,
                    verifier=lambda *_args, **_kwargs: None,
                    sleeper=lambda _: None,
                    timeout=1,
                )


if __name__ == "__main__":
    unittest.main()
