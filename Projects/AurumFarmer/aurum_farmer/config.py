"""Runtime configuration with secret-file references instead of embedded credentials."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any, Mapping


def default_runtime_root() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "BoxBrain" / "AurumFarmer"
    return Path.home() / ".local" / "state" / "boxbrain" / "aurum-farmer"


def default_config_path() -> Path:
    override = os.environ.get("AURUM_FARMER_CONFIG")
    return Path(override).expanduser().resolve() if override else default_runtime_root() / "farmer.json"


def default_config(root: Path | None = None) -> dict[str, Any]:
    runtime = (root or default_runtime_root()).expanduser().resolve()
    return {
        "schema": "aurum.farmer.config.v1",
        "runtime_root": str(runtime),
        "ledger_path": str(runtime / "farmer.sqlite3"),
        "signing_key_path": str(runtime / "farmer-signing.key"),
        "api_token_path": str(runtime / "api.token"),
        "api_host": "127.0.0.1",
        "api_port": 19466,
        "poll_seconds": 2.0,
        "lease_seconds": 90.0,
        "future_branch": {"budget": {"nodes": 256, "workers": 4, "probe_units": 32}, "probes": []},
        "executors": {
            "allowed_programs": [],
            "gh_executable": "gh",
        },
    }


def write_initial_config(path: str | os.PathLike[str], *, root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    destination = Path(path).expanduser().resolve()
    values = default_config(Path(root).expanduser().resolve() if root else destination.parent)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return load_config(destination)
    destination.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    token_path = Path(values["api_token_path"])
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(48), encoding="ascii")
        try:
            os.chmod(token_path, 0o600)
        except OSError:
            pass
    return values


def load_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    destination = Path(path).expanduser().resolve() if path else default_config_path()
    if not destination.exists():
        return write_initial_config(destination)
    values = json.loads(destination.read_text(encoding="utf-8"))
    if values.get("schema") != "aurum.farmer.config.v1":
        raise ValueError("unsupported Aurum Farmer configuration schema")
    if values.get("api_host") not in {"127.0.0.1", "::1", "localhost"} and not values.get("allow_remote_api"):
        raise ValueError("Farmer API must remain loopback-only unless allow_remote_api is explicitly reviewed")
    return values


def read_api_token(config: Mapping[str, Any]) -> str:
    token_path = Path(str(config["api_token_path"])).expanduser().resolve()
    token = token_path.read_text(encoding="ascii").strip()
    if len(token) < 32:
        raise ValueError("Aurum Farmer API token is invalid")
    return token
