"""Action-oriented local BoxBrain node console."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import time
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlencode

from boxbrain.diagnostics import (
    DIAGNOSTIC_AUTHORIZATION,
    TRUST_HOST_KEY_CONFIRMATION,
    DiagnosticError,
)
from boxbrain.links import (
    find_computer,
    load_computers,
    load_node_preferences,
    record_computer,
    set_computer_archived,
    set_node_archived,
    update_saved_connection,
    update_link_connection,
    update_link_profile,
)
from boxbrain.policy import AUTHORIZATION_ASSERTION
from boxbrain.wifi import (
    WIFI_PROVISION_AUTHORIZATION,
    WifiProvisionError,
    connect_wifi,
    list_wifi_networks,
)
from boxbrain.winrm_access import WinRMAccessError, verify_saved_winrm


_COMPUTER_ACTION = re.compile(
    r"^/api/v1/operator/computers/(BB-TARGET-[A-Z0-9-]{6,64})/"
    r"(archive|connect|diagnose|nickname|restore|trust|windows-setup)$",
    re.IGNORECASE,
)
_NODE_ACTION = re.compile(r"^/api/v1/operator/node/(archive|restore|wifi)$", re.IGNORECASE)
_COMPUTER_PAGE = re.compile(r"^/computers/(BB-TARGET-[A-Z0-9-]{6,64})$", re.IGNORECASE)
_COMPUTER_RDP = re.compile(
    r"^/api/v1/operator/computers/(BB-TARGET-[A-Z0-9-]{6,64})/remote-desktop$",
    re.IGNORECASE,
)
_LOOPBACK = {"127.0.0.1", "::1"}
_FORM_LIMIT = 8192


def _status_class(value: str) -> str:
    normalized = value.lower()
    if normalized in {"connected", "online", "healthy", "available", "ready", "completed"}:
        return "good"
    if normalized in {"attention", "critical", "failed", "error"}:
        return "bad"
    return "muted"


def _last_seen(item: dict[str, Any]) -> str:
    checked = str(item.get("last_checked", "")).strip()
    if checked:
        try:
            value = datetime.fromisoformat(checked.replace("Z", "+00:00"))
            return value.astimezone().strftime("%b %-d, %-I:%M %p")
        except (ValueError, OSError):
            return checked
    timestamp = item.get("last_seen")
    if isinstance(timestamp, (int, float)):
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().strftime(
                "%b %-d, %-I:%M %p"
            )
        except (ValueError, OSError, OverflowError):
            pass
    return "Not recorded"


class OperatorConsole:
    """Render local fleet workspaces and execute bounded, loopback-only actions."""

    def __init__(
        self,
        state_directory: str,
        *,
        diagnostics: Any = None,
        storage: Any = None,
        manager: Any = None,
        csrf_token: str | None = None,
    ) -> None:
        self.state_directory = state_directory
        self.diagnostics = diagnostics
        self.storage = storage
        self.manager = manager
        self.csrf_token = csrf_token or secrets.token_urlsafe(32)
        self._wifi_cache: dict[str, Any] = {}
        self._wifi_cache_at = 0.0

    @property
    def node_id(self) -> str:
        return os.environ.get("BOXBRAIN_NODE_ID", "BB-NODE-001")

    @property
    def node_name(self) -> str:
        return os.environ.get("BOXBRAIN_NODE_NAME", "BoxBrain Pi4")

    def handle_get(
        self,
        handler: Any,
        parsed: Any,
        status_factory: Callable[[], dict[str, Any]],
    ) -> bool:
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        notice = query.get("notice", [""])[0]
        error = query.get("error", [""])[0]
        links = load_computers(self.state_directory)
        active_links = [item for item in links if not bool(item.get("archived"))]
        archived_links = [item for item in links if bool(item.get("archived"))]

        remote_desktop_match = _COMPUTER_RDP.fullmatch(path)
        if remote_desktop_match:
            target_id = remote_desktop_match.group(1).upper()
            item = find_computer(self.state_directory, target_id)
            if item is None:
                self._send_json(handler, {"error": "computer_not_found"}, 404)
            else:
                self._send_remote_desktop(handler, item)
            return True

        if path == "/":
            body = self._home(status_factory(), active_links)
            self._send_page(handler, "Home", "home", body, notice, error)
            return True
        if path == "/computers":
            status = status_factory()
            self._send_page(
                handler,
                "Computers",
                "computers",
                self._computers(active_links, status),
                notice,
                error,
            )
            return True
        if path == "/archived":
            self._send_page(
                handler,
                "Archived",
                "archived",
                self._archived(archived_links, status_factory()),
                notice,
                error,
            )
            return True
        computer_match = _COMPUTER_PAGE.fullmatch(path)
        if computer_match:
            target_id = computer_match.group(1).upper()
            item = find_computer(self.state_directory, target_id)
            if item is None:
                self._send_json(handler, {"error": "computer_not_found"}, 404)
            else:
                self._send_page(
                    handler,
                    item["friendly_name"],
                    "computers",
                    self._computer(item),
                    notice,
                    error,
                )
            return True
        if path == "/pi-desktop":
            self._send_page(
                handler,
                "BBPI4 Desktop",
                "node",
                self._pi_desktop(),
                notice,
                error,
            )
            return True
        if path == "/tools":
            self._send_page(
                handler,
                "Tools",
                "tools",
                self._tools(active_links, status_factory()),
                notice,
                error,
            )
            return True
        if path == "/node":
            self._send_page(
                handler,
                self.node_name,
                "node",
                self._node(status_factory(), active_links),
                notice,
                error,
            )
            return True
        return False

    def handle_post(self, handler: Any, parsed: Any) -> bool:
        path = parsed.path.rstrip("/")
        action_match = _COMPUTER_ACTION.fullmatch(path)
        node_action_match = _NODE_ACTION.fullmatch(path)
        if (
            action_match is None
            and node_action_match is None
            and path != "/api/v1/operator/assessments"
        ):
            return False
        if handler.client_address[0] not in _LOOPBACK:
            self._send_json(handler, {"error": "loopback_required"}, 403)
            return True

        form = self._read_form(handler)
        if form is None:
            return True
        if not secrets.compare_digest(form.get("csrf", ""), self.csrf_token):
            self._send_json(handler, {"error": "csrf_rejected"}, 403)
            return True

        if path == "/api/v1/operator/assessments":
            self._start_assessment(handler, form)
            return True

        if node_action_match is not None:
            action = node_action_match.group(1).lower()
            if action in {"archive", "restore"}:
                set_node_archived(self.state_directory, action == "archive")
                self._redirect(
                    handler,
                    "/archived" if action == "archive" else "/computers",
                    notice=(
                        f"{self.node_name} archived. Its state and connections were kept."
                        if action == "archive"
                        else f"{self.node_name} restored to Machines."
                    ),
                )
                return True
            if form.get("confirmation", "").strip().upper() != "Y":
                self._redirect(handler, "/computers", error="Enter Y to change Pi Wi-Fi.")
                return True
            try:
                result = connect_wifi(
                    form.get("ssid", ""),
                    form.get("passphrase", ""),
                    WIFI_PROVISION_AUTHORIZATION,
                )
            except (OSError, WifiProvisionError) as exc:
                self._redirect(handler, "/computers", error=str(exc))
            else:
                self._wifi_cache = {}
                self._wifi_cache_at = 0.0
                self._redirect(
                    handler,
                    "/computers",
                    notice=f"{self.node_name} connected to {result['ssid']}.",
                )
            return True

        target_id = action_match.group(1).upper()
        action = action_match.group(2).lower()
        item = find_computer(self.state_directory, target_id)
        if item is None:
            self._send_json(handler, {"error": "computer_not_found"}, 404)
            return True
        return_path = f"/computers/{quote(target_id)}"

        if action in {"archive", "restore"}:
            try:
                updated = set_computer_archived(
                    self.state_directory,
                    target_id,
                    action == "archive",
                )
            except (KeyError, OSError) as exc:
                self._redirect(handler, return_path, error=str(exc))
            else:
                self._redirect(
                    handler,
                    "/archived" if action == "archive" else "/computers",
                    notice=(
                        f"{updated['friendly_name']} archived. Its history was kept."
                        if action == "archive"
                        else f"{updated['friendly_name']} restored to Machines."
                    ),
                )
            return True

        if action == "nickname":
            try:
                updated = update_link_profile(
                    self.state_directory,
                    target_id,
                    nickname=form.get("nickname", ""),
                )
            except (KeyError, ValueError) as exc:
                self._redirect(handler, return_path, error=str(exc))
            else:
                self._redirect(
                    handler,
                    return_path,
                    notice=f"Saved nickname: {updated['friendly_name']}.",
                )
            return True

        if action == "windows-setup":
            confirmation = form.get("confirmation", "").strip().upper()
            if confirmation != "Y":
                self._redirect(
                    handler,
                    return_path,
                    error="Enter Y to confirm Windows remote-access setup.",
                )
                return True
            self._send_windows_setup(handler, item)
            return True

        if action == "connect":
            available, message = self._probe(
                item,
                preferred_connection=form.get("connection", "automatic"),
                connection_id=form.get("connection_id", ""),
            )
            if available:
                self._redirect(handler, return_path, notice=message)
            else:
                self._redirect(handler, return_path, error=message)
            return True

        if action == "trust":
            if form.get("confirmation", "").strip().upper() != "Y":
                self._redirect(
                    handler,
                    return_path,
                    error="Enter Y to confirm BoxLink trust repair.",
                )
                return True
            repair = getattr(self.diagnostics, "reset_host_trust", None)
            if not callable(repair):
                self._redirect(handler, return_path, error="BoxLink trust repair is unavailable.")
                return True
            try:
                repair(
                    item["address"],
                    DIAGNOSTIC_AUTHORIZATION,
                    TRUST_HOST_KEY_CONFIRMATION,
                )
                update_link_connection(
                    self.state_directory,
                    target_id,
                    status="connected",
                    last_checked=datetime.now(timezone.utc).isoformat(),
                    last_seen=int(time.time()),
                )
            except (DiagnosticError, KeyError, OSError, ValueError) as exc:
                self._redirect(handler, return_path, error=str(exc))
            else:
                self._redirect(
                    handler,
                    return_path,
                    notice=f"BoxLink trust repaired and authenticated for {item['friendly_name']}.",
                )
            return True

        if self.diagnostics is None:
            self._redirect(handler, return_path, error="Diagnostics are unavailable on this node.")
            return True
        try:
            self.diagnostics.diagnose(item["address"], DIAGNOSTIC_AUTHORIZATION)
        except (DiagnosticError, OSError, RuntimeError) as exc:
            self._redirect(handler, return_path, error=str(exc))
        else:
            self._redirect(
                handler,
                return_path,
                notice=f"Diagnostic completed for {item['friendly_name']}.",
            )
        return True

    def _read_form(self, handler: Any) -> dict[str, str] | None:
        try:
            length = int(handler.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 1 <= length <= _FORM_LIMIT:
            self._send_json(handler, {"error": "invalid_request_size"}, 400)
            return None
        content_type = handler.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/x-www-form-urlencoded":
            self._send_json(handler, {"error": "unsupported_content_type"}, 415)
            return None
        try:
            decoded = handler.rfile.read(length).decode("utf-8")
        except UnicodeError:
            self._send_json(handler, {"error": "invalid_form"}, 400)
            return None
        parsed = parse_qs(decoded, keep_blank_values=True, max_num_fields=20)
        return {key: values[0] for key, values in parsed.items() if values}

    def _start_assessment(self, handler: Any, form: dict[str, str]) -> None:
        if self.manager is None:
            self._redirect(handler, "/tools", error="Network assessments are unavailable.")
            return
        try:
            if form.get("authorization", "").strip().upper() != "Y":
                raise ValueError("Enter Y to confirm this authorized private-network assessment.")
            job = self.manager.submit(
                form.get("target", ""),
                form.get("profile", "discovery"),
                AUTHORIZATION_ASSERTION,
            )
        except RuntimeError as exc:
            message = str(exc)
            if "already running" in message:
                self._redirect(
                    handler,
                    "/tools",
                    notice=f"{message} Live progress is shown below.",
                )
            else:
                self._redirect(handler, "/tools", error=message)
            return
        except ValueError as exc:
            self._redirect(handler, "/tools", error=str(exc))
            return
        self._redirect(
            handler,
            "/tools",
            notice=f"Assessment {job['id']} started. Job history will update here.",
        )

    def _probe(
        self,
        item: dict[str, Any],
        *,
        preferred_connection: str = "automatic",
        connection_id: str = "",
    ) -> tuple[bool, str]:
        label = str(item.get("friendly_name", "Computer"))
        connections = item.get("connections", [])
        candidates = (
            [value for value in connections if isinstance(value, dict)]
            if isinstance(connections, list)
            else []
        )
        winrm_paths = [
            value
            for value in candidates
            if value.get("connection_type") == "winrm"
            and value.get("status") in {"available", "connected"}
            and (not connection_id or str(value.get("id", "")) == connection_id)
        ]
        if preferred_connection in {"automatic", "winrm"} and winrm_paths:
            winrm_path = winrm_paths[0]
            checked = datetime.now(timezone.utc).isoformat()
            try:
                identity_file = os.environ.get(
                    "BOXBRAIN_TARGET_IDENTITY",
                    os.path.join(self.state_directory, "identity", "target_ed25519"),
                )
                winrm_item = dict(item)
                winrm_item["address"] = winrm_path.get("address", item.get("address", ""))
                verify_saved_winrm(self.state_directory, identity_file, winrm_item)
                update_saved_connection(
                    self.state_directory,
                    str(item["target_id"]),
                    connection_type="winrm",
                    status="available",
                    last_checked=checked,
                    connection_id=str(winrm_path.get("id", "")),
                )
            except (KeyError, OSError, ValueError, WinRMAccessError) as exc:
                try:
                    update_saved_connection(
                        self.state_directory,
                        str(item["target_id"]),
                        connection_type="winrm",
                        status="unavailable",
                        last_checked=checked,
                        error=str(exc),
                        connection_id=str(winrm_path.get("id", "")),
                    )
                except (KeyError, OSError, ValueError):
                    pass
                if preferred_connection == "winrm":
                    return False, f"{label} rejected its saved WinRM connection ({exc})."
            else:
                return True, f"{label} is connected through its saved authenticated WinRM path."
        if preferred_connection == "winrm":
            return False, f"{label} does not have an available saved WinRM connection."
        boxlink_paths = [
            value
            for value in candidates
            if value.get("connection_type") in {"ssh", "boxlink-ssh"}
            and (not connection_id or str(value.get("id", "")) == connection_id)
        ]
        if not boxlink_paths:
            return False, f"{label} does not have a saved BoxLink connection."
        boxlink_path = min(
            boxlink_paths,
            key=lambda value: (
                value.get("status") not in {"available", "connected"},
                int(value.get("priority", 100)),
                str(value.get("last_seen_at", "")),
            ),
        )
        address = str(boxlink_path.get("address", "")).strip()
        try:
            parsed = ipaddress.ip_address(address)
            if not (parsed.is_private or parsed.is_link_local):
                raise ValueError("The saved address is outside the private network.")
            probe = getattr(self.diagnostics, "probe", None)
            if callable(probe):
                probe(address, DIAGNOSTIC_AUTHORIZATION)
            else:
                with socket.create_connection((address, 22), timeout=3):
                    pass
        except (DiagnosticError, OSError, ValueError) as exc:
            try:
                update_link_connection(
                    self.state_directory,
                    str(item["target_id"]),
                    status="offline",
                    last_checked=datetime.now(timezone.utc).isoformat(),
                    address=address,
                )
            except (KeyError, OSError, ValueError):
                pass
            detail = str(exc).strip()
            suffix = f" ({detail})" if detail else ""
            return (
                False,
                f"{label} is not reachable through BoxLink. Connect its USB/network link "
                f"or wake the computer, then retry{suffix}. If it was reinstalled, open "
                "Details / Advanced and use Repair BoxLink trust.",
            )
        try:
            update_link_connection(
                self.state_directory,
                str(item["target_id"]),
                status="connected",
                last_checked=datetime.now(timezone.utc).isoformat(),
                last_seen=int(time.time()),
                address=address,
            )
        except (KeyError, OSError, ValueError):
            pass
        self._remember_windows_access(item, address)
        path_label = str(boxlink_path.get("friendly_name", "BoxLink"))
        return True, f"{label} is connected. BoxBrain selected {path_label}."

    def _remember_windows_access(self, item: dict[str, Any], address: str) -> None:
        platform = str(item.get("platform", "")).casefold()
        if "windows" not in platform and "microsoft" not in platform:
            return
        open_ports: set[int] = set()
        for port in (3389, 5985, 5986):
            try:
                with socket.create_connection((address, port), timeout=0.4):
                    open_ports.add(port)
            except OSError:
                pass
        now = datetime.now(timezone.utc).isoformat()
        suffix = address.replace(".", "-").replace(":", "-")
        identity_file = os.environ.get(
            "BOXBRAIN_TARGET_IDENTITY",
            os.path.join(self.state_directory, "identity", "target_ed25519"),
        )
        credential_path = os.path.join(
            self.state_directory,
            "credentials",
            f"{item['target_id']}.winrm",
        )
        winrm_ready = bool(open_ports.intersection({5985, 5986})) and os.path.isfile(
            credential_path
        ) and os.path.isfile(identity_file)
        remembered = dict(item)
        existing = remembered.get("connections", [])
        remembered["connections"] = (
            [value for value in existing if isinstance(value, dict)]
            if isinstance(existing, list)
            else []
        ) + [
            {
                "id": f"local-network-{suffix}",
                "friendly_name": "Local",
                "connection_type": "local-network",
                "description": "Current private-network path through this BoxBrain node",
                "status": "available",
                "address": address,
                "last_seen_at": now,
            },
            {
                "id": f"remote-desktop-{suffix}",
                "friendly_name": "Remote Desktop",
                "connection_type": "rdp",
                "description": "Windows desktop on the current private connection",
                "status": "available" if 3389 in open_ports else "setup-required",
                "address": address,
                "ports": [3389] if 3389 in open_ports else [],
                "last_seen_at": now,
            },
            {
                "id": f"winrm-{suffix}",
                "friendly_name": "WinRM",
                "connection_type": "winrm",
                "description": "Authenticated Windows management through this node",
                "status": "available" if winrm_ready else "setup-required",
                "address": address,
                "ports": sorted(open_ports.intersection({5985, 5986})),
                "last_seen_at": now,
            },
        ]
        try:
            record_computer(self.state_directory, remembered)
        except OSError:
            pass

    def _wifi_inventory(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._wifi_cache and now - self._wifi_cache_at < 30:
            return self._wifi_cache
        try:
            inventory = list_wifi_networks()
        except (OSError, WifiProvisionError):
            inventory = {"interface": "wlan0", "current_ssid": "", "networks": []}
        self._wifi_cache = inventory
        self._wifi_cache_at = now
        return inventory

    @staticmethod
    def _node_ip(status: dict[str, Any]) -> str:
        network = status.get("network", {})
        if not isinstance(network, dict):
            return "Unknown"
        interfaces = network.get("interfaces", [])
        if not isinstance(interfaces, list):
            return "Unknown"
        preferred = ("wlan0", "usb0", "bbap0")
        for name in preferred:
            for item in interfaces:
                if not isinstance(item, dict) or item.get("name") != name:
                    continue
                addresses = item.get("addresses", [])
                if isinstance(addresses, list) and addresses:
                    return str(addresses[0])
        return "Unknown"

    def _computer_identity(self, item: dict[str, Any]) -> tuple[str, str, str]:
        wifi = str(item.get("wifi_ssid") or "").strip()
        users = item.get("known_users", [])
        user_values = [str(value) for value in users] if isinstance(users, list) else []
        diagnostics = item.get("diagnostics", {})
        if isinstance(diagnostics, dict):
            wifi = wifi or str(diagnostics.get("wifi_ssid") or "").strip()
            diagnostic_users = diagnostics.get("known_users", [])
            if isinstance(diagnostic_users, list):
                user_values.extend(str(value) for value in diagnostic_users)
            report_name = str(diagnostics.get("report_json", "")).strip()
            if report_name:
                try:
                    report_path = Path(report_name).resolve()
                    state_path = Path(self.state_directory).resolve()
                    if os.path.commonpath((str(report_path), str(state_path))) != str(state_path):
                        raise ValueError("report outside state directory")
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    diagnostic = report.get("diagnostic", {}) if isinstance(report, dict) else {}
                    if isinstance(diagnostic, dict):
                        wifi_state = diagnostic.get("wifi", {})
                        if isinstance(wifi_state, dict):
                            wifi = wifi or str(wifi_state.get("ssid") or "").strip()
                        report_users = diagnostic.get("known_users", [])
                        if isinstance(report_users, list):
                            user_values.extend(str(value) for value in report_users)
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                    pass
        saved_user = str(item.get("user", "")).strip()
        if saved_user:
            user_values.append(saved_user)
        cleaned_users = sorted(
            {value.strip() for value in user_values if value.strip()},
            key=str.casefold,
        )
        return (
            wifi or "Unknown",
            str(item.get("address", "Unknown")) or "Unknown",
            ", ".join(cleaned_users) if cleaned_users else "Unknown",
        )

    @staticmethod
    def _identity_facts(wifi: str, address: str, users: str) -> str:
        return f"""
<div class="machine-facts" aria-label="Machine identity">
  <span><small>Wi-Fi</small><strong>{escape(wifi)}</strong></span>
  <span><small>IP address</small><strong>{escape(address)}</strong></span>
  <span><small>Known users</small><strong>{escape(users)}</strong></span>
</div>"""

    def _wifi_form(self, inventory: dict[str, Any]) -> str:
        networks = inventory.get("networks", [])
        if not isinstance(networks, list):
            networks = []
        options = "".join(
            f'<option value="{escape(str(item.get("ssid", "")))}"'
            f'{" selected" if item.get("current") else ""}>'
            f'{escape(str(item.get("ssid", "Unknown")))} · '
            f'{escape(str(item.get("signal", 0)))}% · '
            f'{escape(str(item.get("security", "Unknown")))}'
            f'{" · saved" if item.get("saved") else ""}</option>'
            for item in networks
            if isinstance(item, dict) and item.get("ssid")
        )
        if not options:
            options = '<option value="" disabled selected>No visible networks</option>'
        return f"""
<div class="wifi-panel"><div><strong>Choose Pi Wi-Fi</strong>
<small>The USB/local console stays available while the Wi-Fi path changes.</small></div>
<form class="wifi-form" method="post" action="/api/v1/operator/node/wifi">
{self._csrf()}<label>Network<select name="ssid" required>{options}</select></label>
<label>Password <small>(blank for saved/open)</small><input type="password" name="passphrase" maxlength="64" autocomplete="new-password"></label>
<label>Confirm<input name="confirmation" required maxlength="1" autocomplete="off" placeholder="Y"></label>
<button>Connect Wi-Fi</button></form></div>"""

    @staticmethod
    def _windows_wlan_panel(status: dict[str, Any]) -> str:
        records = status.get("windows_wlan_inventories", [])
        if not isinstance(records, list):
            records = []
        interface_rows = ""
        profile_rows = ""
        for record in records:
            if not isinstance(record, dict):
                continue
            target = record.get("target", {})
            inventory = record.get("inventory", {})
            if not isinstance(target, dict) or not isinstance(inventory, dict):
                continue
            if inventory.get("credential_material_included") is not False:
                continue
            target_label = str(
                target.get("hostname") or target.get("address") or "Windows target"
            )
            for item in inventory.get("interfaces", []):
                if not isinstance(item, dict):
                    continue
                signal = item.get("signal_percent")
                signal_text = f"{signal}%" if isinstance(signal, int) else "unknown signal"
                ipv4 = ", ".join(str(value) for value in item.get("ipv4", [])) or "no IPv4"
                interface_rows += (
                    "<div class='tool-row'><div>"
                    f"<strong>{escape(target_label)} · {escape(str(item.get('name', 'unknown')))}</strong>"
                    f"<small>{escape(str(item.get('current_ssid') or 'Not connected'))} · "
                    f"{escape(str(item.get('state', 'unknown')))} · {escape(signal_text)} · {escape(ipv4)}</small>"
                    "</div><span class='pill muted'>WLAN</span></div>"
                )
            for item in inventory.get("profiles", []):
                if not isinstance(item, dict):
                    continue
                auto = "auto-connect" if item.get("auto_connect") is True else "manual"
                credential = (
                    "credential available"
                    if item.get("credential_available") is True
                    else "credential not reported"
                )
                profile_rows += (
                    "<div><dt>"
                    f"{escape(target_label)} · {escape(str(item.get('profile', 'unknown')))}"
                    "</dt><dd>"
                    f"{escape(str(item.get('interface', 'unknown')))} · "
                    f"{escape(str(item.get('authentication') or 'unknown'))} / "
                    f"{escape(str(item.get('encryption') or 'unknown'))} · "
                    f"{escape(auto)} · priority {escape(str(item.get('priority', 'unknown')))} · "
                    f"{escape(credential)}"
                    "</dd></div>"
                )
        if not interface_rows:
            interface_rows = (
                "<div class='empty'>No Windows WLAN inventory has been collected.</div>"
            )
        if not profile_rows:
            profile_rows = "<div><dt>Saved profiles</dt><dd>None collected</dd></div>"
        return f"""
<section class="panel">
  <div class="eyebrow">Networks / Windows WLAN interfaces</div>
  <h2>Credential-redacted Windows Wi-Fi inventory</h2>
  <p class="panel-copy">Saved profile metadata only; credential values are never displayed.</p>
  {interface_rows}
  <details class="advanced"><summary>Saved profiles</summary><dl>{profile_rows}</dl></details>
</section>"""

    def _home(self, status: dict[str, Any], links: list[dict[str, Any]]) -> str:
        online = sum(
            str(item.get("status", "offline")) in {"connected", "online", "detected"}
            for item in links
        )
        attention = sum(
            isinstance(item.get("diagnostics"), dict)
            and item["diagnostics"].get("overall") == "attention"
            for item in links
        )
        jobs = self._jobs()
        active = sum(job.get("status") in {"queued", "running"} for job in jobs)
        machine_cards = "".join(self._computer_card(item) for item in links)
        if not machine_cards:
            machine_cards = (
                "<div class='empty'><strong>No remembered computers yet.</strong> "
                "Enroll a computer with BoxLink and it will remain here for later access.</div>"
            )
        return f"""
<section class="hero">
  <div><div class="eyebrow">LOCAL CONTROL</div><h1>Access your BoxBrain</h1>
  <p>Start with the node, choose a remembered computer, then use the best available connection path.</p></div>
  <a class="button secondary" href="/pi-desktop">Open BBPI4 Desktop</a>
</section>
<section class="metrics" aria-label="BoxBrain summary">
  {self._metric("Node", "Online", "good")}
  {self._metric("Computers online", f"{online} of {len(links)}", "good" if online else "muted")}
  {self._metric("Active jobs", str(active), "good" if active else "muted")}
  {self._metric("Needs attention", str(attention), "bad" if attention else "good")}
</section>
<section class="section-head"><div><div class="eyebrow">Every remembered machine</div><h2>Machines</h2></div>
<a href="/computers">Manage computers</a></section>
<section class="machine-grid">{'' if load_node_preferences(self.state_directory).get('archived') else self._node_machine_card(status)}{machine_cards}</section>
{self._windows_wlan_panel(status)}
<section class="quick-grid">
  <a class="quick" href="/tools"><span>Tools</span><strong>Diagnostics &amp; assessments</strong><small>Run real checks and review job history.</small></a>
  <a class="quick" href="/computers"><span>Access</span><strong>Remembered computers</strong><small>Open current and historical connection paths for every computer.</small></a>
</section>
"""

    def _access_row(self, item: dict[str, Any]) -> str:
        status = str(item.get("status", "offline"))
        connections = item.get("connections", [])
        if not isinstance(connections, list):
            connections = []
        candidates = [value for value in connections if isinstance(value, dict)]
        available = [
            value
            for value in candidates
            if str(value.get("status", "")) in {"available", "connected"}
        ]
        preferred = min(
            available or candidates,
            key=lambda value: int(value.get("priority", 100)),
            default=None,
        )
        path_name = (
            str(preferred.get("friendly_name", "Saved connection"))
            if preferred is not None
            else "No path observed"
        )
        target_id = quote(str(item["target_id"]))
        return f"""
<a class="machine-row" href="/computers/{target_id}">
  <span class="device-icon small">PC</span><span class="machine-name"><strong>{escape(str(item['friendly_name']))}</strong>
  <small>{escape(path_name)} &middot; {escape(_last_seen(item))}</small></span>
  <span class="pill {_status_class(status)}">{escape(status)}</span><b class="row-action">Access</b>
</a>"""

    def _computers(self, links: list[dict[str, Any]], status: dict[str, Any]) -> str:
        ordered = sorted(
            links,
            key=lambda item: (item.get("status") != "connected", item["friendly_name"].lower()),
        )
        cards = "".join(self._computer_card(item) for item in ordered)
        if not cards:
            cards = "<div class='empty'>No authorized computers have been remembered.</div>"
        return f"""
<section class="hero compact"><div><div class="eyebrow">Persistent fleet</div><h1>Machines</h1>
<p>Each node, computer, and device has its own box. Open Connections or Tools without hunting through the console.</p></div><a class="button secondary" href="/archived">Archived</a></section>
<section class="machine-grid">{'' if load_node_preferences(self.state_directory).get('archived') else self._node_machine_card(status)}{cards}</section>
"""

    def _archived(self, links: list[dict[str, Any]], status: dict[str, Any]) -> str:
        cards = "".join(self._computer_card(item, archived=True) for item in links)
        if load_node_preferences(self.state_directory).get("archived"):
            cards = self._node_machine_card(status, archived=True) + cards
        if not cards:
            cards = "<div class='empty'>Nothing is archived.</div>"
        return f"""
<a class="back" href="/computers">&larr; Machines</a>
<section class="hero compact"><div><div class="eyebrow">Hidden from fleet</div><h1>Archived</h1>
<p>Archived boxes keep their IDs, users, history, and connection paths. Restore any box to return it to Machines.</p></div></section>
<section class="machine-grid">{cards}</section>"""

    def _node_machine_card(self, status: dict[str, Any], *, archived: bool = False) -> str:
        inventory = self._wifi_inventory()
        current_wifi = str(inventory.get("current_ssid", "")).strip() or "Unknown"
        users = status.get("known_users", [])
        user_text = ", ".join(str(value) for value in users) if isinstance(users, list) and users else "Unknown"
        archive_action = "restore" if archived else "archive"
        archive_label = "Restore to Machines" if archived else "Archive box"
        return f"""
<article class="machine-card node-machine{' archived-machine' if archived else ''}">
  <div class="machine-card-head"><div class="device-icon">PI</div><div><span class="machine-kind">BoxBrain node</span>
  <h3>{escape(self.node_name)}</h3><p class="identity">{escape(self.node_id)}</p></div><span class="pill good">online</span></div>
  {self._identity_facts(current_wifi, self._node_ip(status), user_text)}
  <div class="availability"><strong>3</strong><span>connection types</span><b>LOCAL CONTROL</b></div>
  <details class="machine-dropdown"><summary><span>Connections</span><b>3 available</b></summary>
    <div class="compact-option"><span><strong>BBPI4</strong><small>Remote Desktop</small></span><a class="button secondary" href="/pi-desktop">Open</a></div>
    <div class="compact-option"><span><strong>Local</strong><small>Private node connection</small></span><span class="pill good">available</span></div>
    <div class="compact-option"><span><strong>BoxLink</strong><small>Secure server path</small></span><span class="pill muted">automatic</span></div>
    {self._wifi_form(inventory)}
  </details>
  <details class="machine-dropdown"><summary><span>Tools</span><b>4 tools</b></summary>
    <div class="machine-tools"><a class="button" href="/node">Node controls</a><a class="button secondary" href="/pi-desktop">Desktop</a><a class="button secondary" href="/api/v1/status">Status API</a><form method="post" action="/api/v1/operator/node/{archive_action}">{self._csrf()}<button class="archive-button">{archive_label}</button></form></div>
  </details>
</article>"""

    def _computer_card(self, item: dict[str, Any], *, archived: bool = False) -> str:
        status = str(item.get("status", "offline"))
        diagnostic = item.get("diagnostics", {})
        if not isinstance(diagnostic, dict):
            diagnostic = {}
        overall = str(diagnostic.get("overall", "waiting"))
        raw_target_id = str(item["target_id"])
        target_id = quote(raw_target_id)
        connections = item.get("connections", [])
        if not isinstance(connections, list):
            connections = []
        connection_values = [value for value in connections if isinstance(value, dict)]
        available_count = sum(
            str(value.get("status", "")) in {"available", "connected"}
            for value in connection_values
        )
        connection_rows = "".join(
            self._connection_row(
                raw_target_id,
                value,
                current_address=str(item.get("address", "")),
            )
            for value in connection_values
        ) or "<div class='empty'>No saved connection types.</div>"
        has_boxlink = any(
            value.get("connection_type") in {"ssh", "boxlink-ssh"}
            for value in connection_values
        )
        needs_setup = any(
            value.get("status") == "setup-required" for value in connection_values
        )
        connection_tool = ""
        diagnostic_tool = ""
        if has_boxlink:
            connection_tool = f"""<form method="post" action="/api/v1/operator/computers/{target_id}/connect">
{self._csrf()}<button>Connect automatically</button></form>"""
            diagnostic_tool = f"""<form method="post" action="/api/v1/operator/computers/{target_id}/diagnose">
{self._csrf()}<button>Run diagnostics</button></form>"""
        setup_tool = (
            f'<a class="button secondary" href="/computers/{target_id}#windows-access">Windows setup</a>'
            if needs_setup
            else ""
        )
        wifi, address, users = self._computer_identity(item)
        archive_action = "restore" if archived else "archive"
        archive_label = "Restore to Machines" if archived else "Archive box"
        return f"""
<article class="machine-card{' archived-machine' if archived else ''}">
  <div class="machine-card-head"><div class="device-icon">PC</div><div><span class="machine-kind">Managed computer</span>
  <h3>{escape(str(item['friendly_name']))}</h3><p class="identity">{escape(raw_target_id)}</p></div>
  <span class="pill {_status_class(status)}">{escape(status)}</span></div>
  {self._identity_facts(wifi, address, users)}
  <div class="availability"><strong>{available_count}</strong><span>available paths</span><b class="text-{_status_class(overall)}">{escape(overall)}</b></div>
  <details class="machine-dropdown"><summary><span>Connections</span><b>{available_count} available · {len(connection_values)} saved</b></summary>{connection_rows}</details>
  <details class="machine-dropdown"><summary><span>Tools</span><b>Open actions</b></summary>
    <div class="machine-tools"><a class="button secondary" href="/computers/{target_id}">Open machine</a>{connection_tool}{diagnostic_tool}{setup_tool}<form method="post" action="/api/v1/operator/computers/{target_id}/{archive_action}">{self._csrf()}<button class="archive-button">{archive_label}</button></form></div>
  </details>
  <small class="last-seen">Last seen {escape(_last_seen(item))}</small>
</article>
"""

    def _computer(self, item: dict[str, Any]) -> str:
        target_id = str(item["target_id"])
        encoded_id = quote(target_id)
        status = str(item.get("status", "offline"))
        diagnostic = item.get("diagnostics", {})
        if not isinstance(diagnostic, dict):
            diagnostic = {}
        findings = diagnostic.get("findings", [])
        if not isinstance(findings, list):
            findings = []
        finding_rows = "".join(
            f"<li><span class='pill {_status_class(str(value.get('severity', 'note')))}'>"
            f"{escape(str(value.get('severity', 'note')))}</span><div><strong>"
            f"{escape(str(value.get('title', 'Finding')))}</strong><p>"
            f"{escape(str(value.get('recommendation', 'Review this item.')))}</p></div></li>"
            for value in findings
            if isinstance(value, dict)
        ) or "<li class='empty'>No current findings in the last saved report.</li>"
        connections = item.get("connections", [])
        if not isinstance(connections, list):
            connections = []
        connected = status in {"connected", "online", "detected"}
        has_boxlink = any(
            isinstance(value, dict)
            and value.get("connection_type") in {"ssh", "boxlink-ssh"}
            for value in connections
        )
        connection_copy = (
            "Available now through its authorized BoxLink connection."
            if has_boxlink and connected
            else "Detected on the private network. Choose an available path or finish Windows access setup."
            if connected
            else "Saved for later. Retry when the computer is awake and on USB or the same private network."
        )
        connection_rows = "".join(
            self._connection_row(
                target_id,
                value,
                current_address=str(item.get("address", "")),
            )
            for value in connections
            if isinstance(value, dict)
        ) or "<div class='empty'>No connection methods have been observed yet.</div>"
        needs_windows_setup = any(
            isinstance(value, dict)
            and value.get("connection_type") in {"winrm", "rdp", "outbound-boxlink"}
            and value.get("status") == "setup-required"
            for value in connections
        )
        wifi, address, users = self._computer_identity(item)
        archived = bool(item.get("archived"))
        archive_action = "restore" if archived else "archive"
        archive_label = "Restore to Machines" if archived else "Archive box"
        setup_panel = ""
        if needs_windows_setup:
            setup_panel = f"""
<section class="panel" id="windows-access"><div class="eyebrow">Windows access setup</div><h2>Enable private remote access</h2>
<p class="panel-copy">Creates a computer-specific setup file for an administrator to run on this Windows PC. It enables WinRM and Remote Desktop only for the private network and records the permanent BoxBrain target ID. It does not open either service to the public internet.</p>
<form class="stack-form" method="post" action="/api/v1/operator/computers/{encoded_id}/windows-setup">
{self._csrf()}<label>Enter Y to confirm<input name="confirmation" required maxlength="1" autocomplete="off" placeholder="Y"></label>
<button>Create setup file</button></form></section>"""
        if has_boxlink:
            managed_actions = f"""
  <form class="action-card" method="post" action="/api/v1/operator/computers/{encoded_id}/connect">
    {self._csrf()}<span>Connection</span><strong>Connect with BoxLink</strong>
    <small>Checks the saved private SSH path and chooses it when available.</small><button>Connect / retry</button>
  </form>
  <form class="action-card" method="post" action="/api/v1/operator/computers/{encoded_id}/diagnose">
    {self._csrf()}<span>Computer tool</span><strong>Run diagnostics</strong>
    <small>Refreshes disks, memory, devices, networking, and repair findings through the authorized link.</small>
    <button>Run diagnostic</button>
  </form>"""
        else:
            managed_actions = """
  <a class="action-card" href="#windows-access"><span>Windows access</span><strong>Set up WinRM &amp; Remote Desktop</strong>
    <small>Create the guarded administrator setup file for this computer.</small><b>Set up</b></a>
  <a class="action-card" href="/tools"><span>Network tool</span><strong>Scan connection readiness</strong>
    <small>Refresh which private Windows connection services are available.</small><b>Open tools</b></a>"""
        managed_actions += f"""
  <form class="action-card" method="post" action="/api/v1/operator/computers/{encoded_id}/{archive_action}">
    {self._csrf()}<span>Fleet view</span><strong>{archive_label}</strong>
    <small>{'Return this remembered machine to the main fleet.' if archived else 'Hide this box from the main screen without deleting its history.'}</small>
    <button class="archive-button">{archive_label}</button>
  </form>"""
        return f"""
<a class="back" href="/computers">← All computers</a>
<section class="hero compact"><div><div class="eyebrow">Managed computer</div>
<h1>{escape(str(item['friendly_name']))}</h1><p>{escape(connection_copy)}</p></div>
<span class="pill large {_status_class(status)}">{escape(status)}</span></section>
{self._identity_facts(wifi, address, users)}
<details class="panel workspace-dropdown" open><summary><span><span class="eyebrow">Machine tools</span><strong>Tools</strong></span><b>Open</b></summary>
<section class="action-grid">{managed_actions}</section></details>
<details class="panel workspace-dropdown" open><summary><span><span class="eyebrow">Available paths</span><strong>Connections</strong></span><b>Automatic choice</b></summary>{connection_rows}</details>
{setup_panel}
<details class="panel workspace-dropdown"><summary><span><span class="eyebrow">Saved report</span><strong>Health &amp; attention</strong></span><b>{escape(str(diagnostic.get('overall', 'waiting')))}</b></summary>
<ul class="findings">{finding_rows}</ul></details>
<details class="panel workspace-dropdown"><summary><span><span class="eyebrow">Friendly label</span><strong>Nickname</strong></span><b>Edit</b></summary>
<form class="inline-form" method="post" action="/api/v1/operator/computers/{encoded_id}/nickname">
{self._csrf()}<label>Friendly name<input name="nickname" maxlength="80" required value="{escape(str(item['friendly_name']))}"></label>
<button>Save nickname</button></form></details>
<details class="panel advanced"><summary>Details / Advanced</summary>
<dl><div><dt>BoxBrain target ID</dt><dd>{escape(target_id)}</dd></div>
<div><dt>Original computer name</dt><dd>{escape(str(item.get('hostname', 'Unknown')))}</dd></div>
<div><dt>Private address</dt><dd>{escape(str(item.get('address', 'Unknown')))}</dd></div>
<div><dt>Transport</dt><dd>{escape(str(item.get('transport', 'Unknown')))}</dd></div>
<div><dt>Platform</dt><dd>{escape(str(item.get('platform', 'Unknown')))}</dd></div>
<div><dt>Last checked</dt><dd>{escape(_last_seen(item))}</dd></div></dl>
<div class="security-tool"><div class="eyebrow">Security recovery</div><h3>Repair BoxLink trust</h3>
<p>Use only after this computer was reinstalled or its SSH host key was intentionally replaced. The old trust registry is backed up first.</p>
<form class="stack-form" method="post" action="/api/v1/operator/computers/{encoded_id}/trust">
{self._csrf()}<label>Enter Y to confirm<input name="confirmation" required maxlength="1" autocomplete="off" placeholder="Y"></label>
<button>Repair and authenticate</button></form></div></details>
"""

    def _connection_row(
        self,
        target_id: str,
        connection: dict[str, Any],
        *,
        current_address: str = "",
    ) -> str:
        status = str(connection.get("status", "unknown"))
        connection_type = str(connection.get("connection_type", "other"))
        label = str(connection.get("friendly_name", "Connection"))
        description = str(connection.get("description", "Saved connection method"))
        if connection_type in {"ssh", "boxlink-ssh"}:
            is_current = bool(current_address) and str(
                connection.get("address", "")
            ) == current_address
            label = "BoxLink · Current path" if is_current else "BoxLink · Previous path"
            description = (
                "Best available authorized connection"
                if is_current
                else "Historical connection retained for later retry"
            )
        action = ""
        if connection_type in {"ssh", "boxlink-ssh"}:
            action = f"""<form method="post" action="/api/v1/operator/computers/{quote(target_id)}/connect">
{self._csrf()}<input type="hidden" name="connection" value="boxlink">
<input type="hidden" name="connection_id" value="{escape(str(connection.get('id', '')))}">
<button>{'Connect' if status in {'available', 'connected'} else 'Retry path'}</button></form>"""
        elif connection_type == "winrm" and status in {"available", "connected"}:
            action = f"""<form method="post" action="/api/v1/operator/computers/{quote(target_id)}/connect">
{self._csrf()}<input type="hidden" name="connection" value="winrm">
<input type="hidden" name="connection_id" value="{escape(str(connection.get('id', '')))}">
<button>Verify WinRM</button></form>"""
        elif connection_type == "rdp" and status in {"available", "connected"}:
            action = (
                f'<a class="button secondary" href="/api/v1/operator/computers/'
                f'{quote(target_id)}/remote-desktop">Download RDP</a>'
            )
        elif status == "setup-required":
            action = "<span class='connection-hint'>Setup required</span>"
        elif status in {"available", "connected"}:
            action = "<span class='connection-hint'>Available</span>"
        else:
            action = "<span class='connection-hint'>Saved for later</span>"
        return f"""
<div class="connection-row"><div><strong>{escape(label)}</strong><small>{escape(description)}</small></div>
<div class="connection-action"><span class="pill {_status_class(status)}">{escape(status)}</span>{action}</div></div>"""

    def _send_remote_desktop(self, handler: Any, item: dict[str, Any]) -> None:
        connections = item.get("connections", [])
        paths = [
            value
            for value in connections if isinstance(connections, list)
            and isinstance(value, dict)
            and value.get("connection_type") == "rdp"
            and value.get("status") in {"available", "connected"}
        ]
        if not paths:
            self._send_json(handler, {"error": "remote_desktop_unavailable"}, 409)
            return
        address = str(paths[0].get("address", "")).strip()
        try:
            parsed = ipaddress.ip_address(address)
            if not (parsed.is_private or parsed.is_link_local):
                raise ValueError
        except ValueError:
            self._send_json(handler, {"error": "invalid_remote_desktop_address"}, 409)
            return
        rdp = (
            f"full address:s:{address}\r\n"
            "prompt for credentials:i:1\r\n"
            "authentication level:i:2\r\n"
            "enablecredsspsupport:i:1\r\n"
            "screen mode id:i:2\r\n"
            "smart sizing:i:1\r\n"
        ).encode("utf-8")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(item["friendly_name"])).strip("-")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/x-rdp")
        handler.send_header("Content-Disposition", f'attachment; filename="{safe_name or "BoxBrain"}.rdp"')
        handler.send_header("Content-Length", str(len(rdp)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.end_headers()
        if handler.command != "HEAD":
            handler.wfile.write(rdp)

    def _send_windows_setup(self, handler: Any, item: dict[str, Any]) -> None:
        script = _WINDOWS_REMOTE_SETUP.replace(
            "__BOXBRAIN_TARGET_ID__", str(item["target_id"])
        ).replace(
            "__BOXBRAIN_FRIENDLY_NAME__", str(item["friendly_name"]).replace("'", "''")
        )
        payload = script.encode("utf-8")
        filename = f"BoxBrain-setup-{item['target_id']}.ps1"
        handler.send_response(200)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.end_headers()
        if handler.command != "HEAD":
            handler.wfile.write(payload)

    def _pi_desktop(self) -> str:
        viewer = (
            "http://10.12.194.1:8790/current/vnc.html"
            "?host=127.0.0.1&port=6080&autoconnect=1&resize=scale&reconnect=1"
        )
        return f"""
<a class="back" href="/node">&larr; BoxBrain Pi4</a>
<section class="hero compact"><div><div class="eyebrow">LOCAL CONTROL</div><h1>BBPI4 Desktop</h1>
<p>Full graphical access to the Raspberry Pi through the private BoxBrain USB link. The screen transport remains inside an authenticated SSH tunnel.</p></div><span class="pill large good">available</span></section>
<section class="action-grid">
  <a class="action-card" href="{escape(viewer)}"><span>Pi Desktop</span><strong>Open BBPI4</strong>
  <small>Starts the mobile-scaled noVNC desktop in this browser.</small><b>Open desktop</b></a>
  <a class="action-card" href="/node"><span>Console</span><strong>Node controls</strong>
  <small>Return to connections, KVM, recovery, and node health.</small><b>Open controls</b></a>
</section>
<section class="panel"><div class="eyebrow">Connection options</div><h2>BBPI4</h2>
<div class="connection-row"><div><strong>Remote Desktop</strong><small>Private graphical Pi session</small></div><span class="pill good">available</span></div>
<div class="connection-row"><div><strong>Local</strong><small>Direct USB/private-network path</small></div><span class="pill good">available</span></div>
<div class="connection-row"><div><strong>BoxLink</strong><small>Secure outbound server path for status and control</small></div><span class="pill muted">server path</span></div></section>
<details class="panel advanced"><summary>Details / Advanced</summary><dl>
<div><dt>Viewer address</dt><dd>10.12.194.1:8790</dd></div>
<div><dt>Screen tunnel</dt><dd>127.0.0.1:6080 through BBPI4 SSH</dd></div>
<div><dt>Protocol</dt><dd>VNC carried by WebSocket inside SSH</dd></div></dl></details>"""

    @staticmethod
    def _interface_label(interface: str) -> str:
        return {
            "wlan0": "Wi-Fi network",
            "usb0": "BoxBrain USB network",
            "bbap0": "BoxBrain access point",
            "eth0": "Ethernet network",
        }.get(interface, f"{interface} network")

    def _assessment_target_options(
        self,
        status: dict[str, Any],
        links: list[dict[str, Any]],
    ) -> str:
        network = status.get("network", {})
        interfaces = network.get("interfaces", []) if isinstance(network, dict) else []
        default_route = network.get("default_route", {}) if isinstance(network, dict) else {}
        default_interface = (
            str(default_route.get("interface", ""))
            if isinstance(default_route, dict)
            else ""
        )
        network_choices: list[tuple[int, str, str]] = []
        seen_targets: set[str] = set()
        for item in interfaces if isinstance(interfaces, list) else []:
            if not isinstance(item, dict):
                continue
            interface = str(item.get("name", "unknown"))
            if interface == "lo":
                continue
            details = item.get("networks", [])
            if not isinstance(details, list):
                continue
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                address = str(detail.get("address", "")).strip()
                prefix = detail.get("prefix_length")
                try:
                    connected = ipaddress.ip_network(f"{address}/{int(prefix)}", strict=False)
                except (TypeError, ValueError):
                    continue
                if not isinstance(connected, ipaddress.IPv4Network):
                    continue
                if not (connected.is_private or connected.is_link_local):
                    continue
                if connected.num_addresses > 1024:
                    continue
                target = connected.with_prefixlen
                if target in seen_targets:
                    continue
                seen_targets.add(target)
                label = (
                    f"{self._interface_label(interface)} — {target} "
                    f"(Pi {address})"
                )
                network_choices.append(
                    (0 if interface == default_interface else 1, target, label)
                )
        network_choices.sort(key=lambda value: (value[0], value[2].casefold()))
        network_options = "".join(
            f'<option value="{escape(target)}"{" selected" if index == 0 else ""}>'
            f'{escape(label)}</option>'
            for index, (_, target, label) in enumerate(network_choices)
        )

        computer_options = ""
        seen_hosts: set[str] = set()
        for item in sorted(links, key=lambda value: str(value.get("friendly_name", "")).casefold()):
            address = str(item.get("address", "")).strip()
            try:
                host = ipaddress.ip_address(address)
            except ValueError:
                continue
            if not isinstance(host, ipaddress.IPv4Address):
                continue
            if not (host.is_private or host.is_link_local) or address in seen_hosts:
                continue
            seen_hosts.add(address)
            label = f"{item.get('friendly_name', 'Remembered computer')} — {address}"
            computer_options += (
                f'<option value="{escape(address)}">{escape(str(label))}</option>'
            )
        groups = ""
        if network_options:
            groups += f'<optgroup label="Connected node networks">{network_options}</optgroup>'
        if computer_options:
            groups += f'<optgroup label="Remembered computers">{computer_options}</optgroup>'
        if not groups:
            groups = '<option value="" disabled selected>No connected private targets detected</option>'
        return groups

    def _tools(self, links: list[dict[str, Any]], status: dict[str, Any]) -> str:
        diagnostic_rows = "".join(
            f"<div class='tool-row'><div><strong>{escape(str(item['friendly_name']))}</strong>"
            f"<small>{escape(str(item.get('status', 'offline')))} · {escape(str(item['target_id']))}</small></div>"
            f"<a class='button secondary' href='/computers/{quote(str(item['target_id']))}'>Open tools</a></div>"
            for item in links
        ) or "<div class='empty'>No computers are enrolled for diagnostics.</div>"
        jobs = self._jobs()
        progress_panel = self._scan_progress(jobs)
        job_rows = "".join(self._job_row(job) for job in jobs)
        if not job_rows:
            job_rows = "<div class='empty'>No assessment jobs have run yet.</div>"
        return f"""
<section class="hero compact"><div><div class="eyebrow">Real node actions</div><h1>Tools</h1>
<p>Tools run on this Pi. Unsafe public targets and unconfirmed assessments are rejected by policy.</p></div></section>
<section class="panel"><div class="eyebrow">Computer tools</div><h2>Diagnostics</h2>{diagnostic_rows}</section>
<section class="panel"><div class="eyebrow">Network tool</div><h2>Authorized private assessment</h2>
<form class="stack-form" method="post" action="/api/v1/operator/assessments">
{self._csrf()}<label>Connected private target<select name="target" required>{self._assessment_target_options(status, links)}</select></label>
<small class="field-help">Choose a live network attached to this node, or scan one remembered computer.</small>
<label>Profile<select name="profile"><option value="discovery">Discovery</option><option value="baseline">Baseline services</option></select></label>
<label>Enter Y to confirm authorization<input name="authorization" required maxlength="1" autocomplete="off" placeholder="Y"></label>
<button>Start assessment</button></form></section>
{progress_panel}
<section class="panel"><div class="section-head"><div><div class="eyebrow">History</div><h2>Assessment jobs</h2></div>
<a href="/tools">Refresh</a></div>{job_rows}</section>
"""

    def _scan_progress(self, jobs: list[dict[str, Any]]) -> str:
        active = next(
            (
                job
                for job in jobs
                if str(job.get("status", "")) in {"queued", "running"}
            ),
            None,
        )
        if active is None:
            return ""
        events: list[dict[str, Any]] = []
        if self.storage is not None:
            try:
                loaded = self.storage.list_job_events(str(active.get("id", "")), 10)
                if isinstance(loaded, list):
                    events = [value for value in loaded if isinstance(value, dict)]
            except (OSError, RuntimeError):
                pass
        event_rows = "".join(
            f'<div class="scan-line {escape(str(event.get("level", "info")))}">'
            f'<time>{escape(str(event.get("created_at", ""))[11:19] or "--:--:--")}</time>'
            f'<span>{escape(str(event.get("message", "Working…")))}</span></div>'
            for event in events
        )
        if not event_rows:
            event_rows = (
                '<div class="scan-line info"><time>now</time>'
                '<span>Waiting for the first scan update…</span></div>'
            )
        target = escape(str(active.get("target", "Private network")))
        profile = escape(str(active.get("profile", "discovery")))
        job_id = escape(str(active.get("id", "")))
        return f"""
<section class="panel scan-progress" data-live-scan="true" aria-live="polite">
  <div class="section-head"><div><div class="eyebrow">Live node activity</div><h2>Port scan progress</h2></div>
  <span class="pill muted">{escape(str(active.get('status', 'running')))}</span></div>
  <div class="scan-summary"><strong>{target}</strong><span>{profile} · job {job_id}</span></div>
  <div class="progress-track" aria-label="Scan in progress"><span></span></div>
  <div class="scan-console" role="log">{event_rows}<div class="scan-cursor">BoxBrain is still working…</div></div>
  <small class="field-help">This view refreshes every five seconds until the assessment finishes.</small>
</section>"""

    def _node(self, status: dict[str, Any], links: list[dict[str, Any]]) -> str:
        memory = status.get("memory", {})
        storage = status.get("storage", {})
        connection_map = status.get("connection_map", {})
        transports = connection_map.get("transports", []) if isinstance(connection_map, dict) else []
        connection_rows = "".join(
            f"<div class='tool-row'><div><strong>{escape(str(item.get('label', 'Connection')))}</strong>"
            f"<small>{escape(str(item.get('state', 'unknown')))} · {escape(', '.join(item.get('interfaces', [])) or 'No interface')}</small></div>"
            f"<span class='pill {_status_class(str(item.get('state', 'unknown')))}'>{escape(str(item.get('target_count', 0)))} computers</span></div>"
            for item in transports
            if isinstance(item, dict)
        ) or "<div class='empty'>Connection inventory is unavailable.</div>"
        inventory = self._wifi_inventory()
        current_wifi = str(inventory.get("current_ssid", "")).strip() or "Unknown"
        users = status.get("known_users", [])
        user_text = ", ".join(str(value) for value in users) if isinstance(users, list) and users else "Unknown"
        archived = bool(load_node_preferences(self.state_directory).get("archived"))
        archive_action = "restore" if archived else "archive"
        archive_label = "Restore to Machines" if archived else "Archive box"
        return f"""
<section class="hero compact"><div><div class="eyebrow">BoxBrain node</div><h1>{escape(self.node_name)}</h1>
<p>{escape(self.node_id)} · LOCAL CONTROL · {len(links)} remembered computers</p></div><span class="pill large good">online</span></section>
{self._identity_facts(current_wifi, self._node_ip(status), user_text)}
<details class="panel workspace-dropdown" open><summary><span><span class="eyebrow">Node actions</span><strong>Tools</strong></span><b>3 tools</b></summary><section class="action-grid">
  <a class="action-card" href="/pi-desktop"><span>Remote Desktop</span><strong>Open BBPI4 Desktop</strong><small>Full graphical Pi access through the private SSH screen tunnel.</small><b>Open</b></a>
  <a class="action-card" href="/api/v1/status"><span>Live data</span><strong>Status API</strong><small>Inspect the current node state as JSON.</small><b>Open</b></a>
  <form class="action-card" method="post" action="/api/v1/operator/node/{archive_action}">{self._csrf()}<span>Fleet view</span><strong>{archive_label}</strong><small>Keep all node state while changing whether its box appears in Machines.</small><button class="archive-button">{archive_label}</button></form>
</section></details>
<details class="panel workspace-dropdown" open><summary><span><span class="eyebrow">Friendly paths</span><strong>Connections</strong></span><b>3 types</b></summary>
<div class="connection-row"><div><strong>BBPI4</strong><small>Remote Desktop</small></div><a class="button secondary" href="/pi-desktop">Connect</a></div>
<div class="connection-row"><div><strong>Local</strong><small>Local private-network connection</small></div><span class="pill good">available</span></div>
<div class="connection-row"><div><strong>BoxLink</strong><small>Secure outbound web/server path</small></div><span class="pill muted">automatic</span></div>
{self._wifi_form(inventory)}
</details>
<details class="panel advanced"><summary>Detected node paths</summary>{connection_rows}</details>
<details class="panel advanced"><summary>Details / Advanced</summary><dl>
<div><dt>Persistent node ID</dt><dd>{escape(self.node_id)}</dd></div>
<div><dt>Host device</dt><dd>{escape(str(status.get('hostname', 'Unknown')))}</dd></div>
<div><dt>Model</dt><dd>{escape(str(status.get('model', 'Unknown')))}</dd></div>
<div><dt>Memory available</dt><dd>{escape(str(memory.get('available_bytes', 'Unknown')))}</dd></div>
<div><dt>Storage free</dt><dd>{escape(str(storage.get('free_bytes', 'Unknown')))}</dd></div>
<div><dt>Agent version</dt><dd>{escape(str(status.get('version', 'Unknown')))}</dd></div></dl></details>
"""

    def _jobs(self) -> list[dict[str, Any]]:
        if self.storage is None:
            return []
        try:
            jobs = self.storage.list_jobs(25)
        except (OSError, RuntimeError):
            return []
        return jobs if isinstance(jobs, list) else []

    @staticmethod
    def _job_row(job: dict[str, Any]) -> str:
        status = str(job.get("status", "unknown"))
        last_message = str(job.get("last_message") or "").strip()
        message = f"<small>{escape(last_message)}</small>" if last_message else ""
        return f"""
<div class="tool-row"><div><strong>{escape(str(job.get('target', 'Assessment')))}</strong>
<small>{escape(str(job.get('profile', 'discovery')))} · {escape(str(job.get('created_at', '')))}</small>{message}</div>
<span class="pill {_status_class(status)}">{escape(status)}</span></div>"""

    @staticmethod
    def _metric(label: str, value: str, state: str) -> str:
        return f"<article><span>{escape(label)}</span><strong class='text-{state}'>{escape(value)}</strong></article>"

    def _csrf(self) -> str:
        return f'<input type="hidden" name="csrf" value="{escape(self.csrf_token)}">'

    def _send_page(
        self,
        handler: Any,
        title: str,
        active: str,
        body: str,
        notice: str = "",
        error: str = "",
    ) -> None:
        links = load_computers(self.state_directory)
        html = self._layout(title, active, body, notice, error, links).encode("utf-8")
        handler._send(
            html,
            "text/html; charset=utf-8",
            content_security_policy=(
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                "base-uri 'none'; frame-ancestors 'none'"
            ),
        )

    @staticmethod
    def _send_json(handler: Any, payload: dict[str, Any], status: int) -> None:
        handler._send(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    @staticmethod
    def _redirect(handler: Any, path: str, *, notice: str = "", error: str = "") -> None:
        query = urlencode({key: value for key, value in {"notice": notice, "error": error}.items() if value})
        destination = f"{path}?{query}" if query else path
        handler.send_response(303)
        handler.send_header("Location", destination)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", "0")
        handler.end_headers()

    def _layout(
        self,
        title: str,
        active: str,
        body: str,
        notice: str,
        error: str,
        links: list[dict[str, Any]],
    ) -> str:
        links = [item for item in links if not bool(item.get("archived"))]
        node_archived = bool(load_node_preferences(self.state_directory).get("archived"))
        def nav(key: str, label: str, href: str) -> str:
            current = " active" if active == key else ""
            return f'<a class="{current.strip()}" href="{href}">{label}</a>'

        message = ""
        if notice:
            message += f'<div class="message good">{escape(notice)}</div>'
        if error:
            message += f'<div class="message bad">{escape(error)}</div>'
        computer_links = "".join(
            f'<a class="access-link" href="/computers/{quote(str(item["target_id"]))}">'
            f'<span class="status-dot {_status_class(str(item.get("status", "offline")))}"></span>'
            f'<span><strong>{escape(str(item["friendly_name"]))}</strong>'
            f'<small>{escape(str(item.get("status", "offline")))}</small></span></a>'
            for item in sorted(
                links,
                key=lambda value: (
                    value.get("status") not in {"connected", "online", "detected"},
                    str(value.get("friendly_name", "")).lower(),
                ),
            )
        ) or '<p class="rail-empty">No remembered computers</p>'
        refresh_meta = (
            '<meta http-equiv="refresh" content="5;url=/tools">'
            if 'data-live-scan="true"' in body
            else ""
        )
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{escape(title)} · BoxBrain</title>{refresh_meta}<style>{_CSS}</style></head><body>
<div class="app-shell"><aside class="side-rail">
  <a class="brand rail-brand" href="/"><span class="brain">BB</span><span><strong>BoxBrain</strong><small>{escape(self.node_name)}</small></span></a>
  <span class="control">LOCAL CONTROL</span>
  <div class="rail-group"><p>Console</p>{nav('home', 'Home', '/')}{nav('computers', 'Computers', '/computers')}{nav('tools', 'Tools', '/tools')}{nav('node', 'Node', '/node')}{nav('archived', 'Archived', '/archived')}</div>
  <div class="rail-group access-tree"><p>Access</p>{'' if node_archived else f'<a class="access-link" href="/node"><span class="status-dot good"></span><span><strong>{escape(self.node_name)}</strong><small>{escape(self.node_id)}</small></span></a>'}{computer_links}</div>
  <div class="rail-footer"><span class="status-dot good"></span><span>Node online</span></div>
</aside><div class="workspace">
  <header class="topbar"><a class="brand" href="/"><span class="brain">BB</span><span><strong>BoxBrain</strong><small>{escape(self.node_name)}</small></span></a><span class="control">LOCAL CONTROL</span></header>
  <main>{message}{body}</main>
  <nav class="bottom-nav" aria-label="Primary">{nav('home', 'Home', '/')}{nav('computers', 'Computers', '/computers')}{nav('tools', 'Tools', '/tools')}{nav('node', 'Node', '/node')}</nav>
</div></div>
</body></html>"""

_WINDOWS_REMOTE_SETUP = r'''#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'

$targetId = '__BOXBRAIN_TARGET_ID__'
$friendlyName = '__BOXBRAIN_FRIENDLY_NAME__'
$boxBrainRoot = Join-Path $env:ProgramData 'BoxBrain'
$backupRoot = Join-Path $boxBrainRoot 'backups'
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

$activeProfiles = @(Get-NetConnectionProfile | Where-Object IPv4Connectivity -ne 'Disconnected')
if ($activeProfiles.NetworkCategory -contains 'Public') {
    throw 'An active Windows network is Public. Change the trusted home network to Private, then retry.'
}

$rdpPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server'
$previousRdp = (Get-ItemProperty -Path $rdpPath -Name fDenyTSConnections).fDenyTSConnections
$previousWinRm = (Get-CimInstance Win32_Service -Filter "Name='WinRM'").StartMode
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
[ordered]@{
    target_id = $targetId
    friendly_name = $friendlyName
    changed_at = (Get-Date).ToUniversalTime().ToString('o')
    previous_rdp_denied = $previousRdp
    previous_winrm_start_mode = $previousWinRm
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backupRoot "remote-access-$stamp.json") -Encoding UTF8

Enable-PSRemoting -SkipNetworkProfileCheck -Force
Set-Service WinRM -StartupType Automatic
Start-Service WinRM
Get-NetFirewallRule -DisplayGroup 'Windows Remote Management' -ErrorAction SilentlyContinue |
    Set-NetFirewallRule -Enabled True -Profile Private -RemoteAddress LocalSubnet

Set-ItemProperty -Path $rdpPath -Name fDenyTSConnections -Type DWord -Value 0
Get-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue |
    Set-NetFirewallRule -Enabled True -Profile Private -RemoteAddress LocalSubnet

New-Item -ItemType Directory -Path $boxBrainRoot -Force | Out-Null
[ordered]@{
    target_id = $targetId
    friendly_name = $friendlyName
    server = 'https://boxbrain.arkmatx.com'
    direct_boxlink = 'not-enrolled'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $boxBrainRoot 'target.json') -Encoding UTF8

Write-Host "BoxBrain Windows access is ready for $friendlyName ($targetId)."
Write-Host 'WinRM and Remote Desktop accept private-network traffic only.'
Write-Host 'No public inbound port was created.'
'''


_CSS = r"""
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;--bg:#101114;--card:#1a1b1f;--card2:#23242a;--raised:#2b2c32;--line:#414249;--text:#f7f2e7;--muted:#aaa69d;--yellow:#f6c945;--orange:#f28b2c;--orange2:#ffad3d;--red:#ff776d}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 82% -8%,#50331a 0,transparent 30rem),linear-gradient(180deg,#151619,var(--bg));color:var(--text)}a{color:var(--yellow);text-decoration:none}button,input,select{font:inherit}.topbar{position:sticky;top:0;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px max(18px,calc((100vw - 1120px)/2));background:#141518ed;border-bottom:1px solid var(--line);backdrop-filter:blur(14px)}.brand{display:flex;align-items:center;gap:10px;color:var(--text)}.brand>span:last-child{display:grid}.brand small{color:var(--muted)}.brain,.device-icon{display:grid;place-items:center;width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,var(--yellow),var(--orange));color:#241506;font-weight:950;box-shadow:0 7px 22px #f28b2c35}.control,.eyebrow,.machine-kind{font-size:.7rem;font-weight:900;letter-spacing:.13em;text-transform:uppercase;color:var(--yellow)}.control{border:1px solid #8b6329;border-radius:8px;padding:7px 10px;background:#2a2115}main{width:min(1120px,calc(100% - 32px));margin:0 auto;padding:34px 0 110px}.hero{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding:24px 0 30px}.hero.compact{align-items:center}.hero h1{font-size:clamp(2.3rem,8vw,5rem);line-height:.94;letter-spacing:-.055em;margin:7px 0 13px}.hero.compact h1{font-size:clamp(2.1rem,6vw,3.7rem)}.hero p,.panel-copy{color:#c0bbb1;line-height:1.55;max-width:760px;margin:0}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:38px}.metrics article,.panel,.action-card,.quick{background:linear-gradient(150deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:14px;padding:20px}.metrics span,.action-card>span,.quick>span{display:block;color:var(--muted);font-size:.76rem;text-transform:uppercase;letter-spacing:.08em}.metrics strong{display:block;font-size:1.5rem;margin-top:7px}.section-head,.card-top{display:flex;align-items:center;justify-content:space-between;gap:14px}.section-head{margin:28px 0 14px}.section-head h2,.panel h2{margin:5px 0 0;font-size:1.55rem}.identity{color:var(--muted);font:.72rem ui-monospace,SFMono-Regular,monospace;margin:3px 0 0;overflow-wrap:anywhere}.pill{display:inline-flex;align-items:center;border-radius:6px;padding:5px 8px;font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.04em}.pill.large{font-size:.8rem;padding:8px 12px}.good{color:#241700;background:var(--yellow)}.bad{color:#250704;background:var(--red)}.muted{color:#ddd8cf;background:#484950}.text-good{color:var(--yellow)!important}.text-bad{color:var(--red)!important}.text-muted{color:var(--muted)!important}.button,button,.action-card b{display:inline-flex;justify-content:center;align-items:center;border:0;border-radius:8px;padding:10px 14px;background:linear-gradient(135deg,var(--yellow),var(--orange2));color:#281703;font-weight:900;cursor:pointer}.button{width:100%}.button.secondary{width:auto;background:#2d2922;color:var(--yellow);border:1px solid #83622d}.quick-grid,.action-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:18px}.quick,.action-card{display:flex;flex-direction:column;min-height:165px;color:var(--text)}.quick strong,.action-card strong{font-size:1.12rem;margin:9px 0}.quick small,.action-card small{color:#bcb7ae;line-height:1.45}.action-card button,.action-card b{margin-top:auto;align-self:flex-start}.action-card b{background:#2d2922;border:1px solid #83622d;color:var(--yellow)}form.action-card{margin:0}.panel{margin-top:14px}.findings{list-style:none;padding:0;margin:15px 0 0}.findings li{display:flex;gap:13px;align-items:flex-start;padding:15px 0;border-top:1px solid var(--line)}.findings p{color:#bbb6ad;margin:5px 0 0;line-height:1.45}.inline-form,.stack-form{display:grid;gap:12px;margin-top:15px}.inline-form{grid-template-columns:1fr auto;align-items:end}.inline-form label,.stack-form label{display:grid;gap:7px;color:var(--muted);font-size:.82rem}input,select{width:100%;border:1px solid #5b5c64;border-radius:8px;background:#121316;color:var(--text);padding:11px 12px;outline:none}input:focus,select:focus{border-color:var(--orange);box-shadow:0 0 0 3px #f28b2c22}.stack-form{max-width:680px}.stack-form button{justify-self:start}.tool-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:14px 0;border-top:1px solid var(--line)}.tool-row:first-of-type{margin-top:12px}.tool-row div{display:grid;gap:4px}.tool-row small{color:var(--muted)}.advanced summary{cursor:pointer;color:var(--yellow);font-weight:900}.advanced dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.advanced dl div{background:#141519;border-radius:8px;padding:13px}.advanced dt{color:var(--muted);font-size:.78rem}.advanced dd{margin:5px 0 0;overflow-wrap:anywhere}.message{position:sticky;top:80px;z-index:4;border:1px solid currentColor;border-radius:10px;padding:13px 15px;margin-bottom:14px;background:#24252a;box-shadow:0 10px 35px #0008}.empty{color:var(--muted);padding:18px;border:1px dashed #55565e;border-radius:10px}.back{display:inline-block;margin-top:8px}.bottom-nav{position:fixed;z-index:6;bottom:0;left:50%;transform:translateX(-50%);display:flex;width:min(620px,calc(100% - 24px));padding:8px;gap:5px;margin-bottom:max(10px,env(safe-area-inset-bottom));border:1px solid var(--line);border-radius:14px;background:#191a1eee;box-shadow:0 14px 48px #000;backdrop-filter:blur(18px)}.bottom-nav a{flex:1;text-align:center;padding:11px 5px;border-radius:8px;color:var(--muted);font-size:.82rem;font-weight:800}.bottom-nav a.active{background:#3a2d19;color:var(--yellow)}
.machine-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:15px;align-items:start}.machine-card{position:relative;overflow:hidden;background:linear-gradient(155deg,#26272c,#191a1e 72%);border:1px solid #4a4b52;border-top:3px solid var(--orange);border-radius:14px;padding:18px;box-shadow:0 14px 35px #0003}.machine-card.node-machine{border-top-color:var(--yellow)}.machine-card.archived-machine{border-top-color:#77726a;opacity:.94}.machine-card-head{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:start;gap:12px}.machine-card-head h3{font-size:1.28rem;margin:3px 0}.machine-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:15px 0}.machine-facts>span{display:grid;gap:4px;min-width:0;padding:10px;border:1px solid #3f4046;border-radius:8px;background:#15161a}.machine-facts small{color:var(--muted);font-size:.66rem;font-weight:900;text-transform:uppercase;letter-spacing:.05em}.machine-facts strong{overflow:hidden;color:#f2eee6;font-size:.82rem;text-overflow:ellipsis;white-space:nowrap}.availability{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:8px;margin:14px 0;padding:12px;border:1px solid #3f4046;border-radius:9px;background:#15161a}.availability>strong{font-size:1.45rem;color:var(--yellow)}.availability>span{color:var(--muted);font-size:.78rem}.availability>b{font-size:.7rem;text-transform:uppercase;color:var(--orange2)}.machine-dropdown{border-top:1px solid var(--line)}.machine-dropdown summary,.workspace-dropdown>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 2px;cursor:pointer;list-style:none}.machine-dropdown summary::-webkit-details-marker,.workspace-dropdown>summary::-webkit-details-marker{display:none}.machine-dropdown summary span{font-weight:900}.machine-dropdown summary b,.workspace-dropdown>summary>b{color:var(--orange2);font-size:.74rem;text-transform:uppercase;letter-spacing:.04em}.machine-dropdown[open] summary,.workspace-dropdown[open]>summary{color:var(--yellow)}.compact-option,.connection-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-top:1px solid #393a40}.compact-option>span,.connection-row>div:first-child{display:grid;gap:4px}.compact-option small,.connection-row small,.connection-hint,.last-seen{color:var(--muted)}.compact-option .button,.connection-row>.button{width:auto}.connection-action{display:flex;align-items:center;justify-content:flex-end;gap:8px}.connection-action form{margin:0}.connection-action button{padding:8px 10px}.machine-tools{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:10px 0}.machine-tools form{margin:0}.machine-tools button,.machine-tools .button{width:100%;height:100%}.archive-button{background:#30281f;color:var(--orange2);border:1px solid #805b34}.wifi-panel{display:grid;gap:10px;padding:14px 0;border-top:1px solid #393a40}.wifi-panel>div{display:grid;gap:4px}.wifi-panel small{color:var(--muted)}.wifi-form{display:grid;grid-template-columns:minmax(150px,1.2fr) minmax(150px,1fr) 72px auto;gap:8px;align-items:end}.wifi-form label{display:grid;gap:5px;color:var(--muted);font-size:.72rem}.wifi-form button{white-space:nowrap}.last-seen{display:block;margin-top:12px;font-size:.74rem}.workspace-dropdown>summary>span{display:grid;gap:4px}.workspace-dropdown>summary strong{font-size:1.25rem}.workspace-dropdown>.action-grid{margin-top:5px}.security-tool{border-top:1px solid var(--line);margin-top:18px;padding-top:18px}.security-tool h3{margin:7px 0}.security-tool p{color:var(--muted);line-height:1.5}
.app-shell{min-height:100vh}.workspace{min-width:0}.side-rail{position:fixed;inset:0 auto 0 0;z-index:8;display:flex;flex-direction:column;width:280px;padding:22px 16px 16px;background:#17181b;border-right:1px solid var(--line);overflow-y:auto}.rail-brand{padding:4px 6px 16px}.side-rail>.control{align-self:flex-start;margin:0 6px 20px}.rail-group{display:grid;gap:4px;margin:0 0 22px}.rail-group>p{margin:0 8px 7px;color:#8f8b83;font-size:.68rem;font-weight:900;letter-spacing:.14em;text-transform:uppercase}.rail-group>a{display:flex;align-items:center;gap:10px;padding:10px 11px;border-radius:8px;color:#c1bcb3;font-weight:800}.rail-group>a:hover,.rail-group>a.active{color:#241700;background:var(--yellow)}.access-tree{min-height:0}.access-link>span:last-child{display:grid;min-width:0}.access-link strong,.access-link small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.access-link small{color:inherit;opacity:.7;font-size:.72rem;font-weight:600}.status-dot{flex:0 0 auto;width:9px;height:9px;border-radius:2px;background:#72737a}.status-dot.good{background:var(--yellow)}.status-dot.bad{background:var(--red)}.rail-empty{margin:4px 9px;color:var(--muted);font-size:.8rem}.rail-footer{display:flex;align-items:center;gap:9px;margin-top:auto;padding:14px 10px 2px;color:var(--muted);font-size:.82rem}.side-rail~.workspace main{width:min(1420px,calc(100% - 328px));margin:0 24px 0 304px;padding:34px 0 72px}.side-rail~.workspace .topbar,.side-rail~.workspace .bottom-nav{display:none}
.field-help{display:block;margin-top:-5px;color:var(--muted);line-height:1.4}
.scan-progress{border-color:#7d5d2c;box-shadow:0 0 0 1px #f28b2c18,0 18px 44px #0004}.scan-progress .section-head{margin:0 0 14px}.scan-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.scan-summary>span{color:var(--muted);font:700 .74rem ui-monospace,SFMono-Regular,monospace}.progress-track{height:8px;overflow:hidden;border-radius:99px;background:#111216;border:1px solid #494a50}.progress-track span{display:block;width:38%;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--yellow),var(--orange));animation:scan-sweep 1.7s ease-in-out infinite}.scan-console{display:grid;gap:4px;max-height:260px;overflow:auto;margin:14px 0;padding:13px;border:1px solid #414249;border-radius:9px;background:#0c0d0f;color:#ded9cf;font:600 .78rem/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}.scan-line{display:grid;grid-template-columns:68px minmax(0,1fr);gap:9px}.scan-line time{color:#817d75}.scan-line.success span{color:var(--yellow)}.scan-line.error span{color:var(--red)}.scan-line.warning span{color:var(--orange2)}.scan-cursor{color:var(--orange2);animation:scan-blink 1s steps(2,end) infinite}@keyframes scan-sweep{0%{transform:translateX(-105%)}50%{transform:translateX(85%)}100%{transform:translateX(265%)}}@keyframes scan-blink{50%{opacity:.4}}
@media(max-width:1100px){.side-rail{width:248px}.side-rail~.workspace main{width:calc(100% - 288px);margin-left:272px}.machine-grid{grid-template-columns:1fr}}
@media(max-width:900px){.side-rail{display:none}.side-rail~.workspace main{width:min(1120px,calc(100% - 32px));margin:0 auto;padding:34px 0 110px}.side-rail~.workspace .topbar{display:flex}.side-rail~.workspace .bottom-nav{display:flex}.machine-grid{grid-template-columns:1fr}}
@media(max-width:700px){main{width:min(100% - 24px,1120px);padding-top:18px}.topbar{padding:11px 14px}.control{font-size:.62rem}.hero{display:grid;padding-top:20px}.hero .button{justify-self:start}.metrics{grid-template-columns:1fr 1fr}.machine-grid{grid-template-columns:1fr}.machine-card{padding:15px}.machine-facts{grid-template-columns:1fr 1fr}.machine-facts>span:last-child{grid-column:1/-1}.wifi-form{grid-template-columns:1fr}.wifi-form button{width:100%}.inline-form{grid-template-columns:1fr}.inline-form button{justify-self:start}.action-grid,.quick-grid{grid-template-columns:1fr}.tool-row{align-items:flex-start}.tool-row .button{width:auto}.hero h1{font-size:2.7rem}.machine-tools{grid-template-columns:1fr}.connection-row{align-items:flex-start}.connection-action{flex-direction:column;align-items:flex-end}}
"""
