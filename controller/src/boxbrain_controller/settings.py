from dataclasses import dataclass
from os import getenv
from pathlib import Path
import re

from dotenv import load_dotenv


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPOSITORY_ROOT / ".env.local", override=False)


def _csv_environment(name: str, default: str) -> tuple[str, ...]:
    value = getenv(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _bool_environment(name: str, default: bool) -> bool:
    value = getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _path_environment(name: str, default: Path) -> tuple[Path, ...]:
    value = getenv(name)
    if value is None or not value.strip():
        return (default.resolve(),)
    return tuple(
        Path(item.strip()).expanduser().resolve()
        for item in re.split(r"[;,]", value)
        if item.strip()
    )


def _single_path_environment(name: str, default: Path) -> Path:
    value = getenv(name)
    if value is None or not value.strip():
        return default.resolve()
    return Path(value.strip()).expanduser().resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    repository_root: Path = _REPOSITORY_ROOT
    environment: str = getenv("BOXBRAIN_ENVIRONMENT", "development")
    host: str = getenv("BOXBRAIN_HOST", "127.0.0.1")
    port: int = int(getenv("BOXBRAIN_PORT", "8000"))
    api_token: str | None = getenv("BOXBRAIN_API_TOKEN") or None
    allowed_hosts: tuple[str, ...] = _csv_environment(
        "BOXBRAIN_ALLOWED_HOSTS",
        "127.0.0.1,localhost,testserver",
    )
    cors_origins: tuple[str, ...] = _csv_environment(
        "BOXBRAIN_CORS_ORIGINS",
        (
            "http://localhost:3000,http://localhost:8080,"
            "http://127.0.0.1:8080,https://localhost:8080,"
            "https://127.0.0.1:8080"
        ),
    )
    plugin_dir: Path = _single_path_environment(
        "BOXBRAIN_PLUGIN_DIR",
        _REPOSITORY_ROOT / "plugins",
    )
    observer_plugin_id: str = getenv(
        "BOXBRAIN_OBSERVER_PLUGIN_ID",
        "boxbrain.windows-sandbox-observer",
    )
    observation_policy_path: Path = _single_path_environment(
        "BOXBRAIN_OBSERVATION_POLICY",
        _REPOSITORY_ROOT / "policies" / "observation.json",
    )
    data_dir: Path = _single_path_environment(
        "BOXBRAIN_DATA_DIR",
        _REPOSITORY_ROOT / "controller" / "data",
    )
    sandbox_profile: Path = _single_path_environment(
        "BOXBRAIN_SANDBOX_PROFILE",
        _REPOSITORY_ROOT / "sandbox" / "BoxBrain-Isolated.wsb",
    )
    sandbox_launch_enabled: bool = _bool_environment(
        "BOXBRAIN_SANDBOX_LAUNCH_ENABLED",
        getenv("BOXBRAIN_ENVIRONMENT", "development") == "development",
    )
    kali_pi_agent_url: str = getenv(
        "BOXBRAIN_KALI_PI_AGENT_URL",
        "http://127.0.0.1:8787",
    )
    kali_pi_agent_timeout_seconds: float = float(
        getenv("BOXBRAIN_KALI_PI_AGENT_TIMEOUT_SECONDS", "1.5")
    )
    remote_usb_identity_file: Path = Path(
        getenv(
            "BOXBRAIN_REMOTE_USB_IDENTITY_FILE",
            str(Path.home() / ".ssh" / "boxbrain_pi_ed25519"),
        )
    ).expanduser().resolve()
    agent_runtime_enabled: bool = _bool_environment(
        "BOXBRAIN_AGENT_RUNTIME_ENABLED",
        True,
    )
    agent_model: str = getenv("BOXBRAIN_AGENT_MODEL", "gpt-5.6-sol")
    agent_max_output_tokens: int = int(
        getenv("BOXBRAIN_AGENT_MAX_OUTPUT_TOKENS", "1800")
    )
    diagnostic_executor_enabled: bool = _bool_environment(
        "BOXBRAIN_DIAGNOSTIC_EXECUTOR_ENABLED",
        getenv("BOXBRAIN_ENVIRONMENT", "development") == "development",
    )
    diagnostic_timeout_seconds: float = float(
        getenv("BOXBRAIN_DIAGNOSTIC_TIMEOUT_SECONDS", "20")
    )
    diagnostic_max_output_bytes: int = int(
        getenv("BOXBRAIN_DIAGNOSTIC_MAX_OUTPUT_BYTES", "32768")
    )
    github_copilot_offload_enabled: bool = _bool_environment(
        "BOXBRAIN_GITHUB_COPILOT_OFFLOAD_ENABLED",
        False,
    )
    github_copilot_allowed_roots: tuple[Path, ...] = _path_environment(
        "BOXBRAIN_GITHUB_COPILOT_ALLOWED_ROOTS",
        _REPOSITORY_ROOT,
    )
    github_copilot_timeout_seconds: float = float(
        getenv("BOXBRAIN_GITHUB_COPILOT_TIMEOUT_SECONDS", "120")
    )
    github_copilot_max_files: int = int(
        getenv("BOXBRAIN_GITHUB_COPILOT_MAX_FILES", "100")
    )
    github_copilot_max_file_bytes: int = int(
        getenv("BOXBRAIN_GITHUB_COPILOT_MAX_FILE_BYTES", "32768")
    )
    github_copilot_max_content_bytes: int = int(
        getenv("BOXBRAIN_GITHUB_COPILOT_MAX_CONTENT_BYTES", "131072")
    )
    github_copilot_max_output_bytes: int = int(
        getenv("BOXBRAIN_GITHUB_COPILOT_MAX_OUTPUT_BYTES", "65536")
    )


settings = Settings()
