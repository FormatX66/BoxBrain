"""Controlled, non-exploitative network assessment runner."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Callable
import xml.etree.ElementTree as ET

from boxbrain.policy import validate_target
from boxbrain.storage import Storage, utc_now


MAX_BASELINE_HOSTS = 64
SUPPORTED_PROFILES = {"discovery", "baseline"}

SERVICE_FINDINGS: dict[int, tuple[str, str, str]] = {
    21: (
        "high",
        "Cleartext FTP service exposed",
        "Replace FTP with SFTP or another encrypted file-transfer service.",
    ),
    23: (
        "high",
        "Cleartext Telnet service exposed",
        "Disable Telnet and use SSH with key-based authentication.",
    ),
    80: (
        "low",
        "Unencrypted HTTP service exposed",
        "Confirm that no sensitive data crosses this service, or redirect it to HTTPS.",
    ),
    445: (
        "medium",
        "SMB service reachable",
        "Restrict SMB to required systems and verify signing, patching, and share permissions.",
    ),
    2375: (
        "critical",
        "Unencrypted Docker API exposed",
        "Disable the unauthenticated Docker API or require mutually authenticated TLS.",
    ),
    3389: (
        "medium",
        "Remote Desktop service reachable",
        "Limit RDP to trusted management hosts and require Network Level Authentication and MFA.",
    ),
    5900: (
        "medium",
        "VNC service reachable",
        "Restrict VNC to a protected management channel and require strong authentication.",
    ),
    6379: (
        "high",
        "Redis service reachable",
        "Bind Redis to trusted interfaces and require access controls and network filtering.",
    ),
    9200: (
        "high",
        "Elasticsearch service reachable",
        "Restrict Elasticsearch to trusted clients and require authentication and TLS.",
    ),
    11211: (
        "high",
        "Memcached service reachable",
        "Restrict Memcached to trusted application hosts and block untrusted network access.",
    ),
    27017: (
        "high",
        "MongoDB service reachable",
        "Restrict MongoDB to trusted clients and require authentication and TLS.",
    ),
}


class AssessmentManager:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self._lock = threading.Lock()
        self._active_job: str | None = None
        self._thread: threading.Thread | None = None

    def submit(
        self,
        raw_target: str,
        profile: str,
        authorization: str,
    ) -> dict[str, Any]:
        if profile not in SUPPORTED_PROFILES:
            raise ValueError(f"Unsupported profile: {profile}")
        target = validate_target(raw_target, authorization)

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError(f"Assessment {self._active_job} is already running.")
            job_id = self.storage.create_job(str(target), profile, authorization)
            self._active_job = job_id
            self._thread = threading.Thread(
                target=self._run_job,
                args=(job_id, str(target), profile),
                name=f"boxbrain-assessment-{job_id}",
                daemon=True,
            )
            self._thread.start()

        job = self.storage.get_job(job_id)
        if job is None:
            raise RuntimeError("Assessment job was not created.")
        return job

    def _run_job(self, job_id: str, target: str, profile: str) -> None:
        self.storage.update_job(job_id, status="running", started_at=utc_now(), error=None)
        self.storage.append_job_event(job_id, "Assessment started on the BoxBrain node.")
        try:
            scan_directory = self.storage.state_directory / "scans"
            scan_directory.mkdir(parents=True, exist_ok=True)

            self.storage.append_job_event(job_id, f"Discovering devices on {target}.")
            discovery_xml = self._run_nmap(
                [
                    "--unprivileged",
                    "-sn",
                    "-n",
                    "-T3",
                    "--max-retries",
                    "1",
                    "--host-timeout",
                    "20s",
                    "-PS22,80,443,445,3389",
                    "-oX",
                    "-",
                    target,
                ],
                timeout=360,
                progress=lambda elapsed: self.storage.append_job_event(
                    job_id,
                    f"Device discovery is running — {elapsed}s elapsed.",
                ),
            )
            (scan_directory / f"{job_id}-discovery.xml").write_text(
                discovery_xml,
                encoding="utf-8",
            )
            assets = self._save_hosts(job_id, discovery_xml)
            self.storage.append_job_event(
                job_id,
                f"Device discovery finished — {len(assets)} devices responded.",
                level="success",
            )

            if profile == "baseline" and assets:
                selected = list(assets)[:MAX_BASELINE_HOSTS]
                if len(assets) > MAX_BASELINE_HOSTS:
                    self.storage.save_finding(
                        job_id,
                        None,
                        "low",
                        "Baseline service scan was limited",
                        (
                            f"{len(assets)} live hosts were found; service enumeration was "
                            f"limited to the first {MAX_BASELINE_HOSTS} hosts."
                        ),
                        "Split the authorized network into smaller assessment scopes.",
                    )
                self.storage.append_job_event(
                    job_id,
                    f"Checking common services on {len(selected)} devices.",
                )
                service_xml = self._run_nmap(
                    [
                        "--unprivileged",
                        "-sT",
                        "-n",
                        "-Pn",
                        "-T3",
                        "--top-ports",
                        "100",
                        "--version-light",
                        "--max-retries",
                        "2",
                        "--host-timeout",
                        "90s",
                        "-oX",
                        "-",
                        *selected,
                    ],
                    timeout=max(300, len(selected) * 120),
                    progress=lambda elapsed: self.storage.append_job_event(
                        job_id,
                        f"Service scan is running — {elapsed}s elapsed.",
                    ),
                )
                (scan_directory / f"{job_id}-services.xml").write_text(
                    service_xml,
                    encoding="utf-8",
                )
                self._save_services(job_id, service_xml, assets)
                refreshed = self.storage.get_job(job_id) or {}
                self.storage.append_job_event(
                    job_id,
                    f"Service scan finished — {refreshed.get('service_count', 0)} services recorded.",
                    level="success",
                )

            self.storage.update_job(
                job_id,
                status="completed",
                finished_at=utc_now(),
                error=None,
            )
            report = self.storage.build_report(job_id)
            self.storage.write_report(job_id, render_report_html(report))
            self.storage.append_job_event(
                job_id,
                "Assessment completed and the report is ready.",
                level="success",
            )
        except Exception as error:
            self.storage.update_job(
                job_id,
                status="failed",
                finished_at=utc_now(),
                error=str(error)[:2000],
            )
            self.storage.append_job_event(
                job_id,
                f"Assessment failed: {str(error)[:400]}",
                level="error",
            )
        finally:
            with self._lock:
                self._active_job = None

    @staticmethod
    def _run_nmap(
        arguments: list[str],
        timeout: int,
        progress: Callable[[int], None] | None = None,
    ) -> str:
        try:
            process = subprocess.Popen(
                ["nmap", *arguments],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as error:
            raise RuntimeError(f"Nmap could not start: {error}") from error

        started = time.monotonic()
        while True:
            elapsed = time.monotonic() - started
            remaining = timeout - elapsed
            if remaining <= 0:
                process.kill()
                process.communicate()
                raise RuntimeError("The assessment exceeded its safety timeout.")
            try:
                stdout, stderr = process.communicate(timeout=min(5, remaining))
                break
            except subprocess.TimeoutExpired:
                if progress is not None:
                    try:
                        progress(max(1, round(time.monotonic() - started)))
                    except Exception:
                        pass
        if process.returncode != 0:
            detail = stderr.strip() or stdout.strip()
            raise RuntimeError(f"Nmap failed: {detail[:1000]}")
        return stdout

    def _save_hosts(self, job_id: str, xml_text: str) -> dict[str, int]:
        root = ET.fromstring(xml_text)
        assets: dict[str, int] = {}
        for host in root.findall("host"):
            status = host.find("status")
            if status is None or status.get("state") != "up":
                continue
            addresses = {
                address.get("addrtype"): address
                for address in host.findall("address")
                if address.get("addr")
            }
            ipv4 = addresses.get("ipv4")
            if ipv4 is None or not ipv4.get("addr"):
                continue
            mac = addresses.get("mac")
            hostname_node = host.find("hostnames/hostname")
            asset_id = self.storage.save_asset(
                job_id,
                ipv4.get("addr", ""),
                hostname_node.get("name") if hostname_node is not None else None,
                mac.get("addr") if mac is not None else None,
                mac.get("vendor") if mac is not None else None,
                "up",
            )
            assets[ipv4.get("addr", "")] = asset_id
        return assets

    def _save_services(
        self,
        job_id: str,
        xml_text: str,
        assets: dict[str, int],
    ) -> None:
        root = ET.fromstring(xml_text)
        for host in root.findall("host"):
            ipv4 = next(
                (
                    node.get("addr")
                    for node in host.findall("address")
                    if node.get("addrtype") == "ipv4"
                ),
                None,
            )
            if not ipv4:
                continue
            asset_id = assets.get(ipv4)
            if asset_id is None:
                hostname_node = host.find("hostnames/hostname")
                asset_id = self.storage.save_asset(
                    job_id,
                    ipv4,
                    hostname_node.get("name") if hostname_node is not None else None,
                    None,
                    None,
                    "up",
                )
                assets[ipv4] = asset_id

            for port_node in host.findall("ports/port"):
                state_node = port_node.find("state")
                if state_node is None or state_node.get("state") != "open":
                    continue
                service_node = port_node.find("service")
                port = int(port_node.get("portid", "0"))
                protocol = port_node.get("protocol", "tcp")
                self.storage.save_service(
                    job_id,
                    asset_id,
                    port,
                    protocol,
                    "open",
                    service_node.get("name") if service_node is not None else None,
                    service_node.get("product") if service_node is not None else None,
                    service_node.get("version") if service_node is not None else None,
                )
                rule = SERVICE_FINDINGS.get(port)
                if rule is not None:
                    severity, title, recommendation = rule
                    self.storage.save_finding(
                        job_id,
                        asset_id,
                        severity,
                        title,
                        f"{ipv4} has TCP port {port} open.",
                        recommendation,
                    )


def render_report_html(report: dict[str, Any]) -> str:
    job = report["job"]
    asset_rows = "".join(
        "<tr>"
        f"<td>{escape(str(asset['ip_address']))}</td>"
        f"<td>{escape(str(asset.get('hostname') or '—'))}</td>"
        f"<td>{escape(str(asset.get('vendor') or '—'))}</td>"
        "</tr>"
        for asset in report["assets"]
    )
    service_rows = "".join(
        "<tr>"
        f"<td>{escape(str(service['ip_address']))}</td>"
        f"<td>{escape(str(service['port']))}/{escape(str(service['protocol']))}</td>"
        f"<td>{escape(str(service.get('name') or 'unknown'))}</td>"
        f"<td>{escape(' '.join(filter(None, [service.get('product'), service.get('version')]))) or '—'}</td>"
        "</tr>"
        for service in report["services"]
    )
    finding_rows = "".join(
        "<article class='finding'>"
        f"<span class='severity {escape(finding['severity'])}'>{escape(finding['severity'])}</span>"
        f"<h3>{escape(finding['title'])}</h3>"
        f"<p>{escape(finding['detail'])}</p>"
        f"<p><strong>Recommendation:</strong> {escape(finding['recommendation'])}</p>"
        "</article>"
        for finding in report["findings"]
    )
    if not finding_rows:
        finding_rows = "<p>No rule-based findings were produced by this assessment.</p>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>BoxBrain assessment {escape(job['id'])}</title>
  <style>
    body {{ font-family: system-ui,sans-serif; max-width: 1000px; margin: 40px auto; padding: 0 20px; color: #14211b; }}
    header {{ border-bottom: 3px solid #1a8f57; padding-bottom: 20px; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0; }}
    .pill {{ background: #e8f7ef; border-radius: 999px; padding: 8px 14px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 14px 0 30px; }}
    th,td {{ text-align: left; border-bottom: 1px solid #d8e2dd; padding: 10px 8px; }}
    .finding {{ border: 1px solid #d8e2dd; border-radius: 12px; padding: 16px; margin: 12px 0; }}
    .finding h3 {{ margin: 8px 0; }}
    .severity {{ border-radius: 999px; color: white; padding: 3px 9px; text-transform: uppercase; font-size: .72rem; }}
    .critical {{ background: #7d1128; }} .high {{ background: #b83a2d; }}
    .medium {{ background: #a76600; }} .low {{ background: #2774a8; }}
  </style>
</head>
<body>
  <header>
    <h1>BoxBrain network assessment</h1>
    <p>Authorized scope: <strong>{escape(job['target'])}</strong> · Profile: {escape(job['profile'])}</p>
  </header>
  <div class="summary">
    <span class="pill">{len(report['assets'])} assets</span>
    <span class="pill">{len(report['services'])} open services</span>
    <span class="pill">{len(report['findings'])} findings</span>
  </div>
  <h2>Findings</h2>{finding_rows}
  <h2>Assets</h2>
  <table><thead><tr><th>Address</th><th>Hostname</th><th>Vendor</th></tr></thead><tbody>{asset_rows}</tbody></table>
  <h2>Open services</h2>
  <table><thead><tr><th>Address</th><th>Port</th><th>Service</th><th>Product</th></tr></thead><tbody>{service_rows}</tbody></table>
  <footer>Generated {escape(report['generated_at'])} · BoxBrain evidence report</footer>
</body>
</html>"""
