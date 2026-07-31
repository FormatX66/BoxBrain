"""Local command-line client for BoxBrain."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from boxbrain.diagnostics import DIAGNOSTIC_AUTHORIZATION
from boxbrain.enrollment import LINK_AUTHORIZATION
from boxbrain.patches import (
    PATCH_DELIVERY_AUTHORIZATION,
    PATCH_DELIVERY_CONFIRMATION,
)
from boxbrain.policy import AUTHORIZATION_ASSERTION
from boxbrain.wifi import (
    WIFI_PROVISION_AUTHORIZATION,
    WifiProvisionError,
    provision_current_wifi,
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
    except (RuntimeError, WifiProvisionError) as error:
        print(str(error), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
