from pathlib import Path

import pytest

from boxbrain_controller import sandbox_observer as observer_module
from boxbrain_controller.sandbox_observer import (
    SandboxStartError,
    WindowsSandboxObserver,
)


def test_start_opens_only_the_configured_wsb_profile(
    tmp_path,
    monkeypatch,
) -> None:
    profile = tmp_path / "BoxBrain-Isolated.wsb"
    profile.write_text("<Configuration />", encoding="utf-8")
    observer = WindowsSandboxObserver(
        profile_path=profile,
        start_enabled=True,
    )
    observer._supported = True
    monkeypatch.setattr(observer, "find_window", lambda: None)
    opened: list[str] = []
    monkeypatch.setattr(
        observer_module.os,
        "startfile",
        lambda path: opened.append(path),
        raising=False,
    )

    result = observer.start()

    assert result == "starting"
    assert opened == [str(profile)]


def test_start_rejects_a_non_wsb_profile(tmp_path) -> None:
    profile = tmp_path / "not-a-sandbox.txt"
    profile.write_text("not a profile", encoding="utf-8")
    observer = WindowsSandboxObserver(
        profile_path=profile,
        start_enabled=True,
    )
    observer._supported = True

    with pytest.raises(SandboxStartError, match="fixed profile"):
        observer.start()
