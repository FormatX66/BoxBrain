from __future__ import annotations

from pathlib import Path

from boxbrain_controller.settings import _REPOSITORY_ROOT, settings


def test_default_runtime_paths_are_checkout_anchored() -> None:
    assert settings.plugin_dir == (_REPOSITORY_ROOT / "plugins").resolve()
    assert settings.observation_policy_path == (
        _REPOSITORY_ROOT / "policies" / "observation.json"
    ).resolve()
    assert settings.data_dir == (_REPOSITORY_ROOT / "controller" / "data").resolve()
    assert settings.sandbox_profile == (
        _REPOSITORY_ROOT / "sandbox" / "BoxBrain-Isolated.wsb"
    ).resolve()


def test_default_policy_exists_in_checkout() -> None:
    assert settings.observation_policy_path.is_file()
    assert settings.observation_policy_path.name == "observation.json"
    assert settings.observation_policy_path.parent == Path(
        _REPOSITORY_ROOT / "policies"
    )
