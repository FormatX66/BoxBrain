"""Local command-line client for BoxBrain."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from boxbrain.diagnostics import DIAGNOSTIC_AUTHORIZATION
from boxbrain.enrollment import LINK_AUTHORIZATION
from boxbrain.headless_link import (
    HEADLESS_LINK_AUTHORIZATION,
    HEADLESS_LINK_CONFIRMATION,
    HeadlessLinkError,
    execute_headless_windows_link,
    preview_headless_windows_link,
)
from boxbrain.patches import (
    PATCH_DELIVERY_AUTHORIZATION,
    PATCH_DELIVERY_CONFIRMATION,
)
from boxbrain.policy import AUTHORIZATION_ASSERTION
from boxbrain.rescue_boot import (
    ARM_CONFIRMATION,
    CANCEL_CONFIRMATION,
    IMPORT_CONFIRMATION,
    REBOOT_NORMAL_CONFIRMATION,
    RescueBootError,
    RescueBootManager,
)
from boxbrain.wifi import (
    WIFI_PROVISION_AUTHORIZATION,
    WifiProvisionError,
    provision_current_wifi,
)
from boxbrain.windows_wlan import (
    WLAN_RECONNECT_AUTHORIZATION,
    WLAN_RECONNECT_CONFIRMATION,
)


def _http_request(path: str) -> dict[str, Any]:
    port = os.environ.get("BOXBRAIN_PORT", "8787")
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
            return json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"BoxBrain is unavailable: {error}") from error


def _control_request(
    payload: dict[str, Any],
    timeout: int = 5,
) -> dict[str, Any]:
    socket_path = os.environ.get(
        "BOXBRAIN_CONTROL_SOCKET",
        "/run/boxbrain/control.sock",
    )
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
    chunks: list[bytes] = []
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(socket_path)
            client.sendall(encoded)
            while True:
                chunk = client.recv(64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk or sum(map(len, chunks)) > 4 * 1024 * 1024:
                    break
    except OSError as error:
        raise RuntimeError(f"BoxBrain control socket is unavailable: {error}") from error

    try:
        response = json.loads(b"".join(chunks).split(b"\n", 1)[0])
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError("BoxBrain returned an invalid control response.") from error
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error", "BoxBrain request failed.")))
    return response


def _rescue_manager() -> RescueBootManager:
    return RescueBootManager(
        os.environ.get("BOXBRAIN_STATE_DIR", "/var/lib/boxbrain")
    )


def _usb_keyboard_request(
    action: str,
    *,
    authorized: bool,
    confirmation: str,
    alternate_interface: str,
) -> dict[str, Any]:
    executable = "/usr/local/sbin/boxbrain-usb-keyboard-config"
    command = [executable, action]
    if authorized:
        command.append("--authorized")
    if confirmation:
        command.extend(("--confirmation", confirmation))
    if action == "stage":
        command.extend(("--alternate-interface", alternate_interface))
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=75,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("The USB HID configurator is unavailable.") from error
    if result.returncode != 0:
        message = result.stderr.strip() or "USB HID configuration failed."
        raise RuntimeError(message)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("The USB HID configurator returned invalid data.") from error
    if not isinstance(payload, dict):
        raise RuntimeError("The USB HID configurator returned invalid data.")
    return payload


def _access_point_request(
    action: str,
    *,
    authorized: bool,
    confirmation: str,
) -> dict[str, Any]:
    executable = "/usr/local/sbin/boxbrain-access-point-config"
    command = [executable, action]
    if authorized:
        command.append("--authorized")
    if confirmation:
        command.extend(("--confirmation", confirmation))
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=75,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("The access-point configurator is unavailable.") from error
    if result.returncode != 0:
        message = result.stderr.strip() or "Access-point configuration failed."
        raise RuntimeError(message)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("The access-point configurator returned invalid data.") from error
    if not isinstance(payload, dict):
        raise RuntimeError("The access-point configurator returned invalid data.")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="boxbrainctl",
        description="Control the local BoxBrain Kali Pi edge agent.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("health", help="Show service health.")
    subparsers.add_parser("status", help="Show probe status and latest assessment.")

    jobs = subparsers.add_parser("jobs", help="List recent assessment jobs.")
    jobs.add_argument("--limit", type=int, default=20)

    report = subparsers.add_parser("report", help="Show an assessment report as JSON.")
    report.add_argument("job_id", nargs="?", default="latest")

    subparsers.add_parser("targets", help="List authorized managed systems.")
    add_target = subparsers.add_parser(
        "add-target",
        help="Enroll an authorized target over private-network SSH.",
    )
    add_target.add_argument("address", help="Private or link-local target IPv4 address.")
    add_target.add_argument(
        "--transport",
        choices=("network-ssh",),
        default="network-ssh",
    )
    add_target.add_argument(
        "--authorized",
        action="store_true",
        help="Confirm permission to link this computer.",
    )
    subparsers.add_parser(
        "agent",
        help="Show edge-agent policy, capabilities, and recommendations.",
    )
    subparsers.add_parser(
        "controller",
        help="Compatibility alias for the edge-agent state.",
    )

    target_report = subparsers.add_parser(
        "target-report",
        help="Show the latest read-only system intelligence report.",
    )
    target_report.add_argument("address", help="Authorized target IPv4 address.")

    diagnose = subparsers.add_parser(
        "diagnose",
        help="Refresh system intelligence for an authorized target.",
    )
    diagnose.add_argument("address", help="Authorized target IPv4 address.")
    diagnose.add_argument(
        "--authorized",
        action="store_true",
        help="Confirm permission to diagnose this computer.",
    )

    assess = subparsers.add_parser(
        "assess",
        help="Run a controlled assessment of a directly connected private scope.",
    )
    assess.add_argument("target", help="Authorized IPv4 address or CIDR.")
    assess.add_argument(
        "--profile",
        choices=("discovery", "baseline"),
        default="discovery",
    )
    assess.add_argument(
        "--authorized",
        action="store_true",
        help="Assert that you own or are authorized to assess the target.",
    )
    assess.add_argument("--wait", action="store_true", help="Wait for completion.")
    assess.add_argument("--timeout", type=int, default=900, help="Wait timeout in seconds.")

    wifi_provision = subparsers.add_parser(
        "wifi-provision",
        help="Provision the Pi from an authorized Windows profile received over USB-C.",
    )
    wifi_provision.add_argument(
        "--stdin",
        action="store_true",
        help="Read the protected provisioning payload from standard input.",
    )
    wifi_provision.add_argument(
        "--authorized",
        action="store_true",
        help="Confirm authorization to use the current Windows Wi-Fi profile.",
    )
    wifi_provision.add_argument(
        "--interface",
        default="wlan0",
        help="Pi NetworkManager Wi-Fi interface.",
    )

    windows_wlan = subparsers.add_parser(
        "windows-wlan",
        help="Inventory or reconnect WLAN on an authorized Windows target.",
    )
    windows_wlan.add_argument("address", help="Authorized private target IPv4 address.")
    windows_wlan.add_argument(
        "action",
        choices=("interfaces", "profiles", "status", "diagnose", "reconnect"),
    )
    windows_wlan.add_argument("--profile", default=None)
    windows_wlan.add_argument("--interface", default=None)
    windows_wlan.add_argument("--authorized", action="store_true")
    windows_wlan.add_argument(
        "--confirmation",
        default="",
        help=f"Exact reconnect phrase: {WLAN_RECONNECT_CONFIRMATION}",
    )

    headless_link = subparsers.add_parser(
        "headless-windows-link",
        help="Preview or inject the fixed Windows link through USB HID.",
    )
    headless_link.add_argument(
        "--execute",
        action="store_true",
        help="Send the fixed keystrokes after all explicit gates pass.",
    )
    headless_link.add_argument(
        "--authorized",
        action="store_true",
        help="Confirm authorization for the physically attached computer.",
    )
    headless_link.add_argument(
        "--confirmation",
        default="",
        help=f"Exact confirmation phrase: {HEADLESS_LINK_CONFIRMATION}",
    )
    headless_link.add_argument(
        "--target-address",
        default="10.12.194.2",
        help="Exact target address on the dedicated USB gadget subnet.",
    )

    usb_keyboard = subparsers.add_parser(
        "usb-hid",
        aliases=("usb-keyboard",),
        help="Preview, stage, commit, or roll back composite USB keyboard and mouse HID.",
    )
    usb_keyboard.add_argument(
        "action",
        choices=("preview", "stage", "commit", "rollback"),
        nargs="?",
        default="preview",
    )
    usb_keyboard.add_argument(
        "--authorized",
        action="store_true",
        help="Confirm authorization to change the Pi USB gadget.",
    )
    usb_keyboard.add_argument(
        "--confirmation",
        default="",
        help="Exact action-specific confirmation phrase.",
    )
    usb_keyboard.add_argument(
        "--alternate-interface",
        default="wlan0",
        help="Non-USB management interface required before staging.",
    )

    access_point = subparsers.add_parser(
        "access-point",
        help="Preview, stage, commit, or roll back the isolated recovery access point.",
    )
    access_point.add_argument(
        "action",
        choices=("preview", "stage", "commit", "rollback"),
        nargs="?",
        default="preview",
    )
    access_point.add_argument(
        "--authorized",
        action="store_true",
        help="Confirm authorization to change the Pi recovery access point.",
    )
    access_point.add_argument(
        "--confirmation",
        default="",
        help="Exact action-specific confirmation phrase.",
    )

    rescue = subparsers.add_parser(
        "rescue",
        help="Manage verified one-shot rescue images and next-boot state.",
    )
    rescue_actions = rescue.add_subparsers(dest="rescue_action", required=True)
    rescue_actions.add_parser("status", help="Show one-shot rescue state.")
    rescue_images = rescue_actions.add_parser(
        "images",
        help="List registered rescue images and verify their checksums.",
    )
    rescue_images.add_argument(
        "--no-verify",
        action="store_true",
        help="List metadata without re-reading full image contents.",
    )
    rescue_import = rescue_actions.add_parser(
        "import",
        help="Copy checksum-verified rescue media into the protected image store.",
    )
    rescue_import.add_argument("source", help="Source ISO or image path.")
    rescue_import.add_argument("--id", required=True, dest="image_id")
    rescue_import.add_argument(
        "--kind",
        required=True,
        choices=("kali", "windows", "custom"),
    )
    rescue_import.add_argument(
        "--architecture",
        required=True,
        choices=("arm64", "x86_64", "multi"),
    )
    rescue_import.add_argument(
        "--boot-compatible",
        action="append",
        required=True,
        choices=("bios", "uefi", "pi4"),
    )
    rescue_import.add_argument(
        "--secure-boot",
        required=True,
        choices=("supported", "unsupported", "unknown"),
    )
    signed_group = rescue_import.add_mutually_exclusive_group()
    signed_group.add_argument("--signed", action="store_const", const=True, dest="signed")
    signed_group.add_argument("--unsigned", action="store_const", const=False, dest="signed")
    rescue_import.set_defaults(signed=None)
    rescue_import.add_argument(
        "--write-mode",
        choices=("read-only", "read-write"),
        default="read-only",
    )
    rescue_import.add_argument("--sha256", required=True, dest="expected_sha256")
    rescue_import.add_argument(
        "--checksum-source",
        required=True,
        help="Public official URL or signed manifest used for the expected SHA-256.",
    )
    rescue_import.add_argument("--authorized", action="store_true")
    rescue_import.add_argument(
        "--confirmation",
        default="",
        help=f"Exact confirmation phrase: {IMPORT_CONFIRMATION}",
    )

    rescue_arm = rescue_actions.add_parser(
        "arm",
        help="Arm exactly one rescue boot after hardware and image verification.",
    )
    rescue_arm.add_argument("mode", help="rescue:kali, rescue:windows, or rescue:<image-id>")
    rescue_arm.add_argument(
        "--target-architecture",
        choices=("arm64", "x86_64", "multi"),
        default=None,
    )
    rescue_arm.add_argument("--authorized", action="store_true")
    rescue_arm.add_argument(
        "--confirmation",
        default="",
        help=f"Exact confirmation phrase: {ARM_CONFIRMATION}",
    )

    rescue_cancel = rescue_actions.add_parser("cancel", help="Cancel an armed rescue boot.")
    rescue_cancel.add_argument("--authorized", action="store_true")
    rescue_cancel.add_argument(
        "--confirmation",
        default="",
        help=f"Exact confirmation phrase: {CANCEL_CONFIRMATION}",
    )
    rescue_actions.add_parser(
        "hardware-check",
        help="Check Pi 4 USB-device rescue prerequisites without changing them.",
    )
    rescue_reboot = rescue_actions.add_parser(
        "reboot-normal",
        help="Force the saved next boot to normal; reboot only with --execute.",
    )
    rescue_reboot.add_argument("--execute", action="store_true")
    rescue_reboot.add_argument("--authorized", action="store_true")
    rescue_reboot.add_argument(
        "--confirmation",
        default="",
        help=f"Exact confirmation phrase: {REBOOT_NORMAL_CONFIRMATION}",
    )
    rescue_actions.add_parser(
        "consume-early",
        help="Internal least-privilege early-boot state consumer.",
    )

    subparsers.add_parser(
        "patches",
        help="List checksum-verified patches staged from Google Drive.",
    )
    deliver_patch = subparsers.add_parser(
        "deliver-patch",
        help="Copy one verified patch to a target without executing it.",
    )
    deliver_patch.add_argument("reference", help="Verified patch reference.")
    deliver_patch.add_argument(
        "--authorized",
        action="store_true",
        help="Confirm permission to write into the target link account.",
    )
    deliver_patch.add_argument(
        "--confirmation",
        default="",
        help=f"Exact confirmation phrase: {PATCH_DELIVERY_CONFIRMATION}",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "status"

    try:
        if command == "health":
            payload = _http_request("/health")
        elif command == "status":
            payload = _http_request("/api/v1/status")
        elif command == "jobs":
            payload = _control_request({"action": "jobs", "limit": args.limit})["jobs"]
        elif command == "report":
            payload = _control_request(
                {"action": "report", "job_id": args.job_id}
            )["report"]
        elif command == "targets":
            payload = _control_request({"action": "targets"})["targets"]
        elif command == "add-target":
            if not args.authorized:
                parser.error(
                    "--authorized is required to confirm permission for this computer."
                )
            payload = _control_request(
                {
                    "action": "add_target",
                    "address": args.address,
                    "transport": args.transport,
                    "authorization": LINK_AUTHORIZATION,
                },
                timeout=30,
            )["target"]
        elif command in {"agent", "controller"}:
            payload = _control_request({"action": "agent"})["agent"]
        elif command == "target-report":
            payload = _control_request(
                {"action": "target_report", "address": args.address}
            )["report"]
        elif command == "diagnose":
            if not args.authorized:
                parser.error(
                    "--authorized is required to confirm permission for this computer."
                )
            payload = _control_request(
                {
                    "action": "diagnose",
                    "address": args.address,
                    "authorization": DIAGNOSTIC_AUTHORIZATION,
                },
                timeout=120,
            )["report"]
        elif command == "assess":
            if not args.authorized:
                parser.error(
                    "--authorized is required to confirm permission for this target."
                )
            response = _control_request(
                {
                    "action": "assess",
                    "target": args.target,
                    "profile": args.profile,
                    "authorization": AUTHORIZATION_ASSERTION,
                }
            )
            payload = response["job"]
            if args.wait:
                deadline = time.monotonic() + max(1, args.timeout)
                while payload["status"] in {"queued", "running"}:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Timed out while waiting for the assessment.")
                    time.sleep(1)
                    payload = _control_request(
                        {"action": "job", "job_id": payload["id"]}
                    )["job"]
        elif command == "wifi-provision":
            if not args.stdin:
                parser.error(
                    "--stdin is required so the Wi-Fi passphrase never enters argv."
                )
            if not args.authorized:
                parser.error(
                    "--authorized is required to provision the current Wi-Fi profile."
                )
            payload = provision_current_wifi(
                sys.stdin,
                WIFI_PROVISION_AUTHORIZATION,
                interface=args.interface,
            )
        elif command == "windows-wlan":
            if args.action == "reconnect" and not args.authorized:
                parser.error("--authorized is required to reconnect Windows WLAN.")
            payload = _control_request(
                {
                    "action": "windows_wlan",
                    "wlan_action": args.action,
                    "address": args.address,
                    "profile": args.profile,
                    "interface": args.interface,
                    "authorization": (
                        WLAN_RECONNECT_AUTHORIZATION if args.authorized else ""
                    ),
                    "confirmation": args.confirmation,
                },
                timeout=150 if args.action == "reconnect" else 100,
            )["result"]
        elif command == "headless-windows-link":
            if not args.execute:
                payload = preview_headless_windows_link(
                    target_address=args.target_address,
                )
            else:
                if not args.authorized:
                    parser.error(
                        "--authorized is required for headless Windows deployment."
                    )
                payload = execute_headless_windows_link(
                    HEADLESS_LINK_AUTHORIZATION,
                    args.confirmation,
                    target_address=args.target_address,
                )
        elif command in {"usb-hid", "usb-keyboard"}:
            if args.action != "preview" and not args.authorized:
                parser.error(
                    "--authorized is required to change the Pi USB gadget."
                )
            payload = _usb_keyboard_request(
                args.action,
                authorized=args.authorized,
                confirmation=args.confirmation,
                alternate_interface=args.alternate_interface,
            )
        elif command == "access-point":
            if args.action != "preview" and not args.authorized:
                parser.error(
                    "--authorized is required to change the Pi recovery access point."
                )
            payload = _access_point_request(
                args.action,
                authorized=args.authorized,
                confirmation=args.confirmation,
            )
        elif command == "rescue":
            manager = _rescue_manager()
            if args.rescue_action == "status":
                payload = manager.status()
            elif args.rescue_action == "images":
                payload = {
                    "images": manager.list_images(verify=not args.no_verify)
                }
            elif args.rescue_action == "import":
                if not args.authorized:
                    parser.error("--authorized is required to import rescue media.")
                payload = manager.import_image(
                    args.source,
                    image_id=args.image_id,
                    kind=args.kind,
                    architecture=args.architecture,
                    boot_compatibility=args.boot_compatible,
                    secure_boot=args.secure_boot,
                    signed=args.signed,
                    write_mode=args.write_mode,
                    expected_sha256=args.expected_sha256,
                    checksum_source=args.checksum_source,
                    authorization=args.confirmation,
                )
            elif args.rescue_action == "arm":
                if not args.authorized:
                    parser.error("--authorized is required to arm one-shot rescue.")
                payload = manager.arm(
                    args.mode,
                    target_architecture=args.target_architecture,
                    authorization=args.confirmation,
                )
            elif args.rescue_action == "cancel":
                if not args.authorized:
                    parser.error("--authorized is required to cancel one-shot rescue.")
                payload = manager.cancel(authorization=args.confirmation)
            elif args.rescue_action == "hardware-check":
                payload = manager.hardware_check()
            elif args.rescue_action == "reboot-normal":
                if not args.authorized:
                    parser.error("--authorized is required to select a normal reboot.")
                payload = manager.reboot_normal(
                    authorization=args.confirmation,
                    execute=args.execute,
                )
            elif args.rescue_action == "consume-early":
                payload = manager.consume_early_boot()
            else:
                parser.error(f"Unsupported rescue action: {args.rescue_action}")
                return 2
        elif command == "patches":
            payload = _control_request({"action": "patches"})["patches"]
        elif command == "deliver-patch":
            if not args.authorized:
                parser.error(
                    "--authorized is required to deliver a patch to this computer."
                )
            payload = _control_request(
                {
                    "action": "deliver_patch",
                    "reference": args.reference,
                    "authorization": PATCH_DELIVERY_AUTHORIZATION,
                    "confirmation": args.confirmation,
                },
                timeout=180,
            )["receipt"]
        else:
            parser.error(f"Unsupported command: {command}")
            return 2
    except (HeadlessLinkError, RescueBootError, RuntimeError, WifiProvisionError) as error:
        print(str(error), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
