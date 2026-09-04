"""No radio or system-service mutation: temporary user-service lifetime canary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from types import SimpleNamespace


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=12, check=True)


def wait_file(path):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text())
        time.sleep(.05)
    raise RuntimeError("Synthetic service did not report ready")


def alive(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1][0] != "Z"
    except FileNotFoundError:
        return False


def child(path):
    Path(path).write_text(json.dumps({"pid": os.getpid(), "cgroup": Path("/proc/self/cgroup").read_text()}))
    time.sleep(40)


def parent(mode, path, unit):
    command = [sys.executable, str(Path(__file__).resolve()), "child", path]
    if mode == "coupled":
        subprocess.Popen(command, start_new_session=True)
    elif mode == "independent":
        run("systemd-run", "--user", "--quiet", "--collect", "--service-type=exec", f"--unit={unit}",
            "--property=Restart=no", "--property=TimeoutStopSec=3", "--", *command)
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import aurum_network as network
        network.RUN_DIR = Path(path).parent
        network.uuid.uuid4 = lambda: SimpleNamespace(hex=unit.removeprefix("aurum-wifi-").removesuffix(".service"))
        original_run = network._run
        def adapted(arguments, **kwargs):
            command_start = arguments.index("--") + 1
            # Keep candidate supervision flags. Substitute only the radio daemon
            # with a synthetic forking child and use the unprivileged test manager.
            arguments = [arguments[0], "--user", *arguments[1:command_start], sys.executable,
                         str(Path(__file__).resolve()), "daemon", path, *arguments[command_start + 1:]]
            return original_run(arguments, **kwargs)
        network._run = adapted
        network._command = lambda name: "/usr/bin/" + name
        result = network._start_owned_supplicant("wlan-test", Path(path), "/usr/bin/systemd-run")
        if result.returncode:
            raise RuntimeError("Candidate service did not start: " + result.stdout)
    Path(path + ".parent-ready").write_text(json.dumps({"ready": True}))
    time.sleep(40)


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "child":
            child(sys.argv[2])
        elif sys.argv[1] == "daemon":
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "child", sys.argv[2]])
            wait_file(Path(sys.argv[2]))
            Path(sys.argv[sys.argv.index("-P") + 1]).write_text(str(process.pid))
        else:
            parent(*sys.argv[2:])
        return
    if os.geteuid() == 0:
        raise RuntimeError("This canary must run unprivileged")
    results = []
    with tempfile.TemporaryDirectory(prefix="aurum-wifi-lifetime-") as directory:
        for mode in ("coupled", "independent", "candidate"):
            tag = uuid.uuid4().hex
            parent_unit = f"aurum-wifi-test-parent-{tag}.service"
            child_unit = f"aurum-wifi-{tag}.service"
            evidence = Path(directory) / f"{mode}.json"
            created = [parent_unit] + ([child_unit] if mode != "coupled" else [])
            try:
                run("systemd-run", "--user", "--quiet", "--collect", "--service-type=exec", f"--unit={parent_unit}",
                    "--property=TimeoutStopSec=3", "--", sys.executable, str(Path(__file__).resolve()),
                    "parent", mode, str(evidence), child_unit)
                observed = wait_file(evidence)
                wait_file(Path(str(evidence) + ".parent-ready"))
                expected_unit = parent_unit if mode == "coupled" else child_unit
                if expected_unit not in observed["cgroup"]:
                    raise RuntimeError("Unexpected synthetic process ownership")
                run("systemctl", "--user", "stop", parent_unit)
                survived = alive(observed["pid"])
                if survived != (mode != "coupled"):
                    raise AssertionError(f"Unexpected {mode} child lifetime")
                result = {"mode": mode, "child_survived_parent_stop": survived, "cgroup_owner_verified": True}
                if mode == "candidate":
                    pid_path = Path(directory) / "wpa-wlan-test.pid"
                    if int(pid_path.read_text()) != observed["pid"]:
                        raise AssertionError("Candidate PID file mismatch")
                    run("systemctl", "--user", "stop", child_unit)
                    if alive(observed["pid"]) or pid_path.exists():
                        raise AssertionError("Candidate cleanup did not finish")
                    result["pidfile_and_service_cleanup_verified"] = True
                results.append(result)
            finally:
                for unit in reversed(created):
                    # Names are generated above; never enumerate or stop unrelated units.
                    subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, timeout=8)
    print(json.dumps({"status": "passed", "uid": os.geteuid(), "network_operations": [],
                      "physical_hopper_changes": [], "cases": results}, indent=2))


if __name__ == "__main__":
    main()
