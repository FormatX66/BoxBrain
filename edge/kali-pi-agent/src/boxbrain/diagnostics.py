"""Read-only diagnostics for computers that authorized a BoxBrain SSH link."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from boxbrain.links import load_links


DIAGNOSTIC_AUTHORIZATION = "I am authorized to diagnose this computer"
WINDOWS_SCRIPT = r"""$ErrorActionPreference = 'SilentlyContinue'
$version = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
Add-Type -AssemblyName Microsoft.VisualBasic
$computer = New-Object Microsoft.VisualBasic.Devices.ComputerInfo
$disks = @(
    [IO.DriveInfo]::GetDrives() |
        Where-Object { $_.DriveType -eq [IO.DriveType]::Fixed -and $_.IsReady } |
        ForEach-Object {
            [ordered]@{
                name = [string]$_.Name
                filesystem = [string]$_.DriveFormat
                size_bytes = [int64]$_.TotalSize
                free_bytes = [int64]$_.AvailableFreeSpace
            }
        }
)
$adapters = @(
    [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
        Where-Object {
            $_.OperationalStatus -eq [Net.NetworkInformation.OperationalStatus]::Up
        } |
        ForEach-Object {
            $properties = $_.GetIPProperties()
            [ordered]@{
                name = [string]$_.Description
                addresses = @(
                    $properties.UnicastAddresses |
                        ForEach-Object { [string]$_.Address }
                )
                gateway = @(
                    $properties.GatewayAddresses |
                        ForEach-Object { [string]$_.Address }
                )
                dns = @(
                    $properties.DnsAddresses |
                        ForEach-Object { [string]$_ }
                )
            }
        }
)
$deviceErrors = @()
try {
    $deviceErrors = @(
        Get-PnpDevice -PresentOnly -ErrorAction Stop |
            Where-Object { $_.Status -notin @('OK','Unknown') } |
            Select-Object -First 25 FriendlyName,Class,Status,Problem
    )
} catch {}
$pendingReboot = $false
$rebootPaths = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending',
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
)
foreach ($path in $rebootPaths) {
    if (Test-Path $path) { $pendingReboot = $true }
}
$uptimeSeconds = [int64](
    [Diagnostics.Stopwatch]::GetTimestamp() / [Diagnostics.Stopwatch]::Frequency
)
$lastBoot = [DateTime]::UtcNow.AddSeconds(-$uptimeSeconds).ToString('o')
$displayVersion = [string]$version.DisplayVersion
if (-not $displayVersion) { $displayVersion = [string]$version.ReleaseId }
$build = [string]$version.CurrentBuildNumber
if ($version.UBR -ne $null) { $build = "$build.$($version.UBR)" }
$productName = [string]$version.ProductName
if ([int]$version.CurrentBuildNumber -ge 22000) {
    $productName = $productName -replace 'Windows 10','Windows 11'
}
$result = [ordered]@{
    schema_version = 1
    family = 'windows'
    hostname = [string]$env:COMPUTERNAME
    os_name = $productName
    os_version = "$displayVersion (build $build)"
    architecture = [string]$env:PROCESSOR_ARCHITECTURE
    last_boot = $lastBoot
    uptime_seconds = $uptimeSeconds
    memory_total_bytes = [int64]$computer.TotalPhysicalMemory
    memory_free_bytes = [int64]$computer.AvailablePhysicalMemory
    disks = $disks
    network_adapters = $adapters
    device_error_count = [int]$deviceErrors.Count
    device_errors = $deviceErrors
    pending_reboot = [bool]$pendingReboot
}
$result | ConvertTo-Json -Depth 7 -Compress
"""


class DiagnosticError(RuntimeError):
    """Raised when a target diagnostic cannot be completed safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_address(address: str) -> str:
    parsed = ipaddress.ip_address(address)
    if parsed.version != 4 or not (parsed.is_private or parsed.is_link_local):
        raise DiagnosticError("Target diagnostics require a private or link-local IPv4 address.")
    return str(parsed)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}-",
        suffix=".json",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _number(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def analyze(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    findings: list[dict[str, str]] = []
    metrics: dict[str, Any] = {}

    disk_percentages: list[float] = []
    for disk in payload.get("disks", []):
        size = _number(disk.get("size_bytes"))
        free = _number(disk.get("free_bytes"))
        if not size or free is None or size <= 0:
            continue
        free_percent = round((free / size) * 100, 1)
        disk["free_percent"] = free_percent
        disk_percentages.append(free_percent)
        name = str(disk.get("name") or disk.get("mount") or "disk")
        if free_percent < 5:
            findings.append(
                {
                    "severity": "high",
                    "title": f"{name} is critically low on space",
                    "detail": f"Only {free_percent:.1f}% of the disk is free.",
                    "recommendation": (
                        "Back up important files, remove safe temporary data, and inspect "
                        "large files before attempting upgrades, optimization, or repair."
                    ),
                }
            )
        elif free_percent < 15:
            findings.append(
                {
                    "severity": "medium",
                    "title": f"{name} is running low on space",
                    "detail": f"{free_percent:.1f}% of the disk remains free.",
                    "recommendation": (
                        "Review storage usage and create additional free space before "
                        "installing updates."
                    ),
                }
            )
    metrics["lowest_disk_free_percent"] = min(disk_percentages) if disk_percentages else None

    total_memory = _number(payload.get("memory_total_bytes"))
    free_memory = _number(payload.get("memory_free_bytes"))
    if total_memory and free_memory is not None and total_memory > 0:
        memory_percent = round((free_memory / total_memory) * 100, 1)
        metrics["memory_free_percent"] = memory_percent
        if memory_percent < 5:
            findings.append(
                {
                    "severity": "high",
                    "title": "Very little memory is available",
                    "detail": f"Only {memory_percent:.1f}% of physical memory is available.",
                    "recommendation": (
                        "Close unnecessary applications and inspect high-memory processes "
                        "before continuing resource-intensive work."
                    ),
                }
            )
        elif memory_percent < 12:
            findings.append(
                {
                    "severity": "medium",
                    "title": "Available memory is low",
                    "detail": f"{memory_percent:.1f}% of physical memory is available.",
                    "recommendation": (
                        "Review running applications and memory use before starting "
                        "resource-intensive diagnostics."
                    ),
                }
            )
    else:
        metrics["memory_free_percent"] = None

    device_error_count = _number(payload.get("device_error_count")) or 0
    metrics["device_error_count"] = device_error_count
    if device_error_count:
        findings.append(
            {
                "severity": "medium",
                "title": "Windows reports device problems",
                "detail": f"{device_error_count} device(s) reported a non-zero error code.",
                "recommendation": (
                    "Review the listed devices, their physical connections, and signed "
                    "manufacturer drivers."
                ),
            }
        )

    if payload.get("pending_reboot"):
        findings.append(
            {
                "severity": "low",
                "title": "A restart is pending",
                "detail": "Windows indicates that an update or component operation needs a restart.",
                "recommendation": (
                    "Save the user's work and schedule a controlled restart before deeper work."
                ),
            }
        )

    if not payload.get("network_adapters"):
        findings.append(
            {
                "severity": "high",
                "title": "No active network configuration was reported",
                "detail": "The target did not report an IP-enabled network adapter.",
                "recommendation": (
                    "Check network hardware, airplane mode, cabling, and adapter drivers."
                ),
            }
        )

    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    highest = max((severity_rank.get(item["severity"], 0) for item in findings), default=0)
    overall = "attention" if highest >= 3 else "review" if highest >= 1 else "healthy"
    return overall, findings, metrics


def render_report(report: dict[str, Any]) -> str:
    target = report["target"]
    diagnostic = report["diagnostic"]
    summary = report["summary"]
    disk_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('name') or item.get('mount') or 'disk'))}</td>"
        f"<td>{escape(str(item.get('filesystem') or 'unknown'))}</td>"
        f"<td>{escape(str(item.get('free_percent', 'unknown')))}%</td>"
        "</tr>"
        for item in diagnostic.get("disks", [])
    ) or '<tr><td colspan="3">No disk information was returned.</td></tr>'
    finding_rows = "".join(
        "<article class='finding'>"
        f"<span class='severity {escape(item['severity'])}'>{escape(item['severity'])}</span>"
        f"<h3>{escape(item['title'])}</h3>"
        f"<p>{escape(item['detail'])}</p>"
        f"<p><strong>Next step:</strong> {escape(item['recommendation'])}</p>"
        "</article>"
        for item in summary["findings"]
    ) or "<p>No system health findings were produced by this read-only check.</p>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BoxBrain target diagnostic</title>
<style>
:root {{ color-scheme: dark; font-family: Inter,ui-sans-serif,system-ui,sans-serif; }}
body {{ margin:0; background:#07100d; color:#e9fff5; }}
main {{ width:min(940px,calc(100% - 32px)); margin:40px auto; }}
h1 {{ font-size:clamp(2rem,6vw,4rem); letter-spacing:-.05em; margin:.2em 0; }}
.eyebrow {{ color:#62f5a7; text-transform:uppercase; letter-spacing:.13em; font-weight:700; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin:24px 0; }}
.card,.panel,.finding {{ background:#0d1b16; border:1px solid #203b30; border-radius:16px; padding:18px; }}
.label {{ color:#8eaa9e; font-size:.8rem; text-transform:uppercase; }}
.value {{ font-size:1.2rem; font-weight:650; margin-top:6px; overflow-wrap:anywhere; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ text-align:left; padding:10px; border-bottom:1px solid #203b30; }}
.finding {{ margin-top:12px; }} .finding h3 {{ margin:8px 0; }}
.severity {{ display:inline-block; border-radius:999px; padding:4px 9px; text-transform:uppercase; font-size:.72rem; font-weight:750; }}
.severity.high {{ background:#5d1c25; color:#ffb7c0; }} .severity.medium {{ background:#5b4614; color:#ffe59b; }}
.severity.low {{ background:#173d5b; color:#a9d8ff; }}
footer {{ color:#688075; margin-top:20px; }}
</style></head><body><main>
<div class="eyebrow">Read-only system intelligence assessment</div>
<h1>{escape(str(target.get('hostname') or target['address']))}</h1>
<div class="grid">
  <div class="card"><div class="label">System status</div><div class="value">{escape(summary['overall'])}</div></div>
  <div class="card"><div class="label">Operating system</div><div class="value">{escape(str(diagnostic.get('os_name') or diagnostic.get('family') or 'unknown'))}</div></div>
  <div class="card"><div class="label">Version</div><div class="value">{escape(str(diagnostic.get('os_version') or 'unknown'))}</div></div>
  <div class="card"><div class="label">Findings</div><div class="value">{len(summary['findings'])}</div></div>
</div>
<section class="panel"><h2>Storage</h2><table><thead><tr><th>Disk</th><th>Filesystem</th><th>Free</th></tr></thead><tbody>{disk_rows}</tbody></table></section>
<section><h2>Optimization and repair priorities</h2>{finding_rows}</section>
<footer>Generated {escape(report['generated_at'])} · BoxBrain · observation only; no changes were performed</footer>
</main></body></html>"""


class TargetDiagnostics:
    def __init__(
        self,
        state_directory: str,
        identity_file: str = "/var/lib/boxbrain/identity/target_ed25519",
    ) -> None:
        self.state_directory = Path(state_directory)
        self.identity_file = Path(identity_file)
        self.links_directory = self.state_directory / "links"
        self.report_directory = self.state_directory / "target-reports"

    def _link(self, address: str) -> dict[str, Any]:
        safe_address = _safe_address(address)
        for item in load_links(str(self.state_directory)):
            if item.get("address") == safe_address and item.get("status") == "connected":
                return item
        raise DiagnosticError("Target is not an authorized, connected BoxBrain link.")

    def _ssh(
        self,
        address: str,
        command: str,
        *,
        input_text: str | None = None,
        timeout: int = 45,
    ) -> str:
        arguments = [
            "ssh",
            "-i",
            str(self.identity_file),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={self.state_directory / 'identity' / 'target_known_hosts'}",
            f"boxbrain-link@{address}",
            command,
        ]
        try:
            result = subprocess.run(
                arguments,
                input=input_text,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise DiagnosticError(f"SSH diagnostic failed: {error}") from error
        if result.returncode != 0:
            message = result.stderr.strip().splitlines()
            detail = message[-1] if message else "remote command failed"
            raise DiagnosticError(f"Target diagnostic failed: {detail[:300]}")
        return result.stdout

    def _windows(self, address: str) -> dict[str, Any]:
        output = self._ssh(
            address,
            (
                'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass '
                '-Command "$script=[Console]::In.ReadToEnd(); Invoke-Expression $script"'
            ),
            input_text=WINDOWS_SCRIPT,
            timeout=90,
        )
        for line in reversed(output.splitlines()):
            if line.lstrip().startswith("{"):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    return payload
        raise DiagnosticError("Windows returned no usable diagnostic data.")

    def _linux(self, address: str) -> dict[str, Any]:
        script = r"""
set -eu
hostname_value=$(hostname 2>/dev/null || printf unknown)
os_name=Linux
os_version=$(uname -r 2>/dev/null || printf unknown)
if [ -r /etc/os-release ]; then
    . /etc/os-release
    os_name=${PRETTY_NAME:-${NAME:-Linux}}
    os_version=${VERSION_ID:-$(uname -r 2>/dev/null || printf unknown)}
fi
memory_total=$(awk '/^MemTotal:/ {print $2 * 1024}' /proc/meminfo 2>/dev/null | cut -d. -f1)
memory_free=$(awk '/^MemAvailable:/ {print $2 * 1024}' /proc/meminfo 2>/dev/null | cut -d. -f1)
printf 'BB|family|linux\n'
printf 'BB|hostname|%s\n' "$hostname_value"
printf 'BB|os_name|%s\n' "$os_name"
printf 'BB|os_version|%s\n' "$os_version"
printf 'BB|architecture|%s\n' "$(uname -m 2>/dev/null || printf unknown)"
printf 'BB|memory_total_bytes|%s\n' "${memory_total:-0}"
printf 'BB|memory_free_bytes|%s\n' "${memory_free:-0}"
df -P -B1 2>/dev/null | awk 'NR > 1 && $2 ~ /^[0-9]+$/ {printf "BB|disk|%s|%s|%s|%s\n",$6,$2,$4,$1}'
if command -v ip >/dev/null 2>&1; then
    ip -o -4 address show up 2>/dev/null | awk '{printf "BB|adapter|%s|%s\n",$2,$4}'
fi
"""
        output = self._ssh(address, "sh -s", input_text=script, timeout=45)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "family": "linux",
            "disks": [],
            "network_adapters": [],
            "pending_reboot": False,
            "device_error_count": 0,
        }
        for line in output.splitlines():
            if not line.startswith("BB|"):
                continue
            parts = line.split("|")
            if len(parts) >= 6 and parts[1] == "disk":
                payload["disks"].append(
                    {
                        "mount": parts[2],
                        "size_bytes": _number(parts[3]) or 0,
                        "free_bytes": _number(parts[4]) or 0,
                        "filesystem": parts[5],
                    }
                )
            elif len(parts) >= 4 and parts[1] == "adapter":
                payload["network_adapters"].append(
                    {"name": parts[2], "addresses": [parts[3]]}
                )
            elif len(parts) >= 3:
                key = parts[1]
                value: Any = "|".join(parts[2:])
                if key in {"memory_total_bytes", "memory_free_bytes"}:
                    value = _number(value) or 0
                payload[key] = value
        return payload

    def diagnose(
        self,
        address: str,
        authorization: str,
    ) -> dict[str, Any]:
        if authorization != DIAGNOSTIC_AUTHORIZATION:
            raise DiagnosticError("Explicit target diagnostic authorization is required.")
        link = self._link(address)
        platform = str(link.get("platform", "")).lower()
        if "windows" in platform:
            diagnostic = self._windows(address)
        else:
            diagnostic = self._linux(address)

        overall, findings, metrics = analyze(diagnostic)
        generated_at = utc_now()
        report = {
            "schema_version": 1,
            "generated_at": generated_at,
            "mode": "read-only",
            "target": {
                "address": address,
                "hostname": link.get("hostname"),
                "transport": link.get("transport"),
            },
            "diagnostic": diagnostic,
            "summary": {
                "overall": overall,
                "finding_count": len(findings),
                "findings": findings,
                "metrics": metrics,
            },
        }

        self.report_directory.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "-", address)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = self.report_directory / f"{safe_name}-{stamp}.json"
        html_path = self.report_directory / f"{safe_name}-{stamp}.html"
        latest_json = self.report_directory / f"{safe_name}-latest.json"
        latest_html = self.report_directory / f"{safe_name}-latest.html"
        _atomic_json(json_path, report)
        _atomic_json(latest_json, report)
        html = render_report(report)
        html_path.write_text(html, encoding="utf-8")
        latest_html.write_text(html, encoding="utf-8")

        link_path = self.links_directory / f"{address.replace('.', '-')}.json"
        current = link
        try:
            loaded = json.loads(link_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        current["diagnostics"] = {
            "status": "completed",
            "overall": overall,
            "last_run": generated_at,
            "finding_count": len(findings),
            "findings": findings,
            "metrics": metrics,
            "report_json": str(latest_json),
            "report_html": str(latest_html),
        }
        _atomic_json(link_path, current)
        return report

    def latest_report(self, address: str) -> dict[str, Any]:
        safe_address = _safe_address(address)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "-", safe_address)
        path = self.report_directory / f"{safe_name}-latest.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise DiagnosticError("No target diagnostic report is available.") from error
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise DiagnosticError(f"Target diagnostic report is unreadable: {error}") from error
        if not isinstance(payload, dict):
            raise DiagnosticError("Target diagnostic report is invalid.")
        return payload
