import json
import os
from pathlib import Path

import pytest

from boxbrain_controller.plugin_process import (
    ObserverPluginClient,
    PluginProcessError,
)
from boxbrain_controller.plugin_registry import PluginRegistry


PLUGIN_ID = "boxbrain.windows-sandbox-observer"
CAPABILITIES = ["observation.describe", "observation.frame"]


def _write_plugin(
    tmp_path: Path,
    body: str,
    *,
    capabilities: list[str] | None = None,
    manifest_updates: dict[str, object] | None = None,
) -> PluginRegistry:
    plugin_dir = tmp_path / "observer"
    plugin_dir.mkdir()
    script = (
        "import base64\n"
        "import hashlib\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "import time\n"
        "request = json.loads(sys.stdin.readline())\n"
        + body
    )
    (plugin_dir / "plugin.py").write_text(script, encoding="utf-8")
    manifest: dict[str, object] = {
        "id": PLUGIN_ID,
        "name": "Test observer",
        "version": "0.1.0",
        "description": "Test-only observer process.",
        "enabled": True,
        "protocol_version": "1",
        "entrypoint": "plugin.py",
        "process_boundary": "out-of-process",
        "target_id": "windows-sandbox",
        "capabilities": capabilities or CAPABILITIES,
    }
    manifest.update(manifest_updates or {})
    (plugin_dir / "boxbrain_plugin.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return PluginRegistry(tmp_path)


def _description_result() -> str:
    return """
result = {
    "target_id": "windows-sandbox",
    "target_name": "Windows Sandbox",
    "connected": "BOXBRAIN_API_TOKEN" in os.environ,
    "window_title": str(os.getpid()),
    "input_enabled": False,
}
print(json.dumps({
    "protocol_version": "1",
    "plugin_id": request["plugin_id"],
    "request_id": request["request_id"],
    "ok": True,
    "result": result,
    "error": None,
}))
"""


def test_observer_runs_separately_without_controller_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("BOXBRAIN_API_TOKEN", "secret-that-must-not-cross")
    registry = _write_plugin(tmp_path, _description_result())

    description = ObserverPluginClient(registry, PLUGIN_ID).describe()

    assert description.connected is False
    assert int(description.window_title) != os.getpid()
    assert description.input_enabled is False


def test_observer_rejects_response_identity_spoofing(tmp_path: Path) -> None:
    body = _description_result().replace(
        '"plugin_id": request["plugin_id"]',
        '"plugin_id": "attacker.observer"',
    )
    client = ObserverPluginClient(_write_plugin(tmp_path, body), PLUGIN_ID)

    with pytest.raises(PluginProcessError, match="identity did not match"):
        client.describe()


def test_observer_validates_png_digest(tmp_path: Path) -> None:
    body = """
frame = b"\\x89PNG\\r\\n\\x1a\\nframe"
print(json.dumps({
    "protocol_version": "1",
    "plugin_id": request["plugin_id"],
    "request_id": request["request_id"],
    "ok": True,
    "result": {
        "target_id": "windows-sandbox",
        "media_type": "image/png",
        "sha256": hashlib.sha256(frame).hexdigest(),
        "data_base64": base64.b64encode(frame).decode("ascii"),
    },
    "error": None,
}))
"""
    client = ObserverPluginClient(_write_plugin(tmp_path, body), PLUGIN_ID)

    assert client.capture_png() == b"\x89PNG\r\n\x1a\nframe"


def test_observer_requires_the_complete_capability_set(tmp_path: Path) -> None:
    registry = _write_plugin(
        tmp_path,
        _description_result(),
        capabilities=["observation.describe"],
    )

    with pytest.raises(PluginProcessError, match="approved capability"):
        ObserverPluginClient(registry, PLUGIN_ID).describe()


def test_observer_response_limit_is_enforced_while_streaming(
    tmp_path: Path,
) -> None:
    registry = _write_plugin(
        tmp_path,
        'sys.stdout.write("x" * 4096)\nsys.stdout.flush()\ntime.sleep(1)\n',
    )
    client = ObserverPluginClient(
        registry,
        PLUGIN_ID,
        timeout_seconds=1,
        max_response_bytes=128,
    )

    with pytest.raises(PluginProcessError, match="exceeded its limit"):
        client.describe()


def test_observer_rejects_additional_input_capability(tmp_path: Path) -> None:
    registry = _write_plugin(
        tmp_path,
        _description_result(),
        capabilities=[
            "observation.describe",
            "observation.frame",
            "input.keyboard",
        ],
    )

    with pytest.raises(PluginProcessError, match="approved capability"):
        ObserverPluginClient(registry, PLUGIN_ID).describe()


def test_observer_process_timeout_is_enforced(tmp_path: Path) -> None:
    registry = _write_plugin(tmp_path, "time.sleep(1)\n")
    client = ObserverPluginClient(
        registry,
        PLUGIN_ID,
        timeout_seconds=0.05,
    )

    with pytest.raises(PluginProcessError, match="did not complete"):
        client.describe()


def test_registry_rejects_entrypoint_traversal_and_extra_fields(
    tmp_path: Path,
) -> None:
    registry = _write_plugin(
        tmp_path,
        _description_result(),
        manifest_updates={
            "entrypoint": "../plugin.py",
            "unexpected": True,
        },
    )

    assert registry.discover() == []
    assert registry.get(PLUGIN_ID) is None
