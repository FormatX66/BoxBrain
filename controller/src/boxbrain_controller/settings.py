from dataclasses import dataclass
from os import getenv
from pathlib import Path

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
    plugin_dir: Path = Path(
        getenv("BOXBRAIN_PLUGIN_DIR", "../plugins")
    ).resolve()
    observer_plugin_id: str = getenv(
        "BOXBRAIN_OBSERVER_PLUGIN_ID",
        "boxbrain.windows-sandbox-observer",
    )
    observation_policy_path: Path = Path(
        getenv(
            "BOXBRAIN_OBSERVATION_POLICY",
            "../policies/observation.json",
        )
    ).resolve()
    data_dir: Path = Path(getenv("BOXBRAIN_DATA_DIR", "./data")).resolve()
    sandbox_profile: Path = Path(
        getenv(
            "BOXBRAIN_SANDBOX_PROFILE",
            "../sandbox/BoxBrain-Isolated.wsb",
        )
    ).resolve()
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


settings = Settings()
