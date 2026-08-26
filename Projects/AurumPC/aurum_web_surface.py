#!/usr/bin/env python3
"""Physical HTML projection client for Hopper.

This process is launched on Hopper's graphical VT by the root-owned projection
runtime.  It grants the dedicated unprivileged Aurum UI user access to the local
X display, launches a sandboxed kiosk browser against the loopback-only Aurum
GUI server, and writes physical-display evidence.  It never exposes a raw shell
through the HTML surface.
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import shutil
import signal
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

SCHEMA = "aurum.desktop.gen1-html-projection"
STOP = False


def _atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _stop(_sig: int, _frame: object) -> None:
    global STOP
    STOP = True


def _browser() -> str | None:
    configured = os.environ.get("AURUM_WEB_RENDERER", "").strip()
    if configured and Path(configured).is_file():
        return configured
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _server_ready(url: str) -> bool:
    try:
        request = urllib.request.Request(url.rstrip("/") + "/api/status", headers={"Host": "127.0.0.1:8765"})
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status == 200
    except Exception:
        return False



def _display_geometry(text: str):
    match = re.search(r"^(\S+)\s+connected(?:\s+primary)?(?:\s+(\d+)x(\d+)\+\d+\+\d+)?(?:\s+(normal|left|right|inverted))?", text, re.MULTILINE)
    if not match or not match.group(2) or not match.group(3):
        return None
    return {"output": match.group(1), "width": int(match.group(2)), "height": int(match.group(3)), "rotation": match.group(4) or "normal"}


def _force_landscape() -> dict[str, Any]:
    xrandr = shutil.which("xrandr")
    if not xrandr:
        return {"status": "unavailable", "reason": "xrandr-unavailable"}
    def query():
        result = subprocess.run([xrandr, "--query"], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8)
        return result.returncode, result.stdout
    try:
        code, raw = query()
        if code != 0:
            return {"status": "failed", "reason": "xrandr-query-failed", "detail": raw[-600:]}
        before = _display_geometry(raw)
        if before is None:
            return {"status": "unavailable", "reason": "active-output-unavailable"}
        if before["rotation"] != "normal" or before["width"] < before["height"]:
            subprocess.run([xrandr, "--output", before["output"], "--rotate", "normal"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        _, raw = query()
        after = _display_geometry(raw)
        if after and after["width"] < after["height"]:
            subprocess.run([xrandr, "--output", after["output"], "--rotate", "right"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            _, raw = query()
            after = _display_geometry(raw)
        if after and after["width"] >= after["height"]:
            return {"status": "landscape", **after, "changed": after != before}
        return {"status": "degraded", "reason": "landscape-not-confirmed", "before": before, "after": after}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "reason": f"{type(exc).__name__}:{exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum Hopper HTML physical projection")
    parser.add_argument("--url", default="http://127.0.0.1:8765/")
    parser.add_argument("--state-dir", type=Path, default=Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state")))
    parser.add_argument("--run-dir", type=Path, default=Path(os.environ.get("AURUM_RUN_DIR", "/run/aurum")))
    parser.add_argument("--ui-user", default=os.environ.get("AURUM_UI_USER", "aurum-ui"))
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    state_path = args.state_dir / "desktop-ui.json"
    pid_path = args.run_dir / "aurum-web-surface.pid"
    args.run_dir.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")

    browser = _browser()
    if browser is None:
        _atomic(state_path, {"schema": SCHEMA, "status": "failed", "reason": "browser-unavailable", "renderer": "html5"})
        pid_path.unlink(missing_ok=True)
        return 1
    try:
        account = pwd.getpwnam(args.ui_user)
    except KeyError:
        _atomic(state_path, {"schema": SCHEMA, "status": "failed", "reason": "ui-user-unavailable", "renderer": "html5"})
        pid_path.unlink(missing_ok=True)
        return 1

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not _server_ready(args.url):
        time.sleep(0.25)
    if not _server_ready(args.url):
        _atomic(state_path, {"schema": SCHEMA, "status": "failed", "reason": "loopback-gui-unavailable", "renderer": "html5"})
        pid_path.unlink(missing_ok=True)
        return 1

    xhost = shutil.which("xhost")
    if not xhost:
        _atomic(state_path, {"schema": SCHEMA, "status": "failed", "reason": "xhost-unavailable", "renderer": "html5"})
        pid_path.unlink(missing_ok=True)
        return 1
    grant = subprocess.run([xhost, f"+SI:localuser:{args.ui_user}"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if grant.returncode != 0:
        _atomic(state_path, {"schema": SCHEMA, "status": "failed", "reason": "x-display-grant-failed", "renderer": "html5"})
        pid_path.unlink(missing_ok=True)
        return 1

    orientation = _force_landscape()

    home = Path(account.pw_dir)
    profile = home / "chromium-profile"
    profile.mkdir(parents=True, exist_ok=True)
    try:
        os.chown(profile, account.pw_uid, account.pw_gid)
    except PermissionError:
        pass
    runuser = shutil.which("runuser")
    if not runuser:
        _atomic(state_path, {"schema": SCHEMA, "status": "failed", "reason": "runuser-unavailable", "renderer": "html5"})
        pid_path.unlink(missing_ok=True)
        return 1

    command = [
        runuser, "-u", args.ui_user, "--",
        "/usr/bin/env",
        f"HOME={home}",
        f"DISPLAY={os.environ.get('DISPLAY', ':0')}",
        browser,
        "--kiosk",
        "--start-fullscreen",
        "--no-first-run",
        "--disable-session-crashed-bubble",
        "--disable-translate",
        "--disable-features=TranslateUI",
        "--disable-pinch",
        "--overscroll-history-navigation=0",
        f"--user-data-dir={profile}",
        f"--app={args.url}",
    ]
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(1.0)
    if process.poll() is not None:
        _atomic(state_path, {"schema": SCHEMA, "status": "failed", "reason": "browser-exited", "returncode": process.returncode, "renderer": "html5"})
        pid_path.unlink(missing_ok=True)
        return 1

    _atomic(state_path, {
        "schema": SCHEMA,
        "generation_name": "Gen1 polished physical surface",
        "status": "running",
        "surface": "physical",
        "renderer": "html5",
        "orientation": orientation,
        "url": args.url,
        "browser": Path(browser).name,
        "browser_user": args.ui_user,
        "browser_sandbox_disabled": False,
        "loopback_only": True,
        "host_actuation": "bounded-control-plane",
        "raw_shell": False,
        "pid": os.getpid(),
        "browser_pid": process.pid,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    while not STOP and process.poll() is None:
        time.sleep(0.5)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    _atomic(state_path, {
        "schema": SCHEMA,
        "generation_name": "Gen1 polished physical surface",
        "status": "stopped",
        "surface": "physical",
        "renderer": "html5",
        "stopped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    pid_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
