from dataclasses import dataclass
from os import getenv
from pathlib import Path


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
            "http://127.0.0.1:8080"
        ),
    )
    plugin_dir: Path = Path(
        getenv("BOXBRAIN_PLUGIN_DIR", "../plugins")
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


settings = Settings()

