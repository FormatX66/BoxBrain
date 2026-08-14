from __future__ import annotations

import gzip
from pathlib import Path
import platform
import subprocess
from typing import Callable


def capture_seed_config(
    output: Path,
    *,
    proc_root: Path = Path("/proc"),
    boot_root: Path = Path("/boot"),
    kernel_release: str | None = None,
) -> Path:
    release = kernel_release or platform.release()
    proc_config = proc_root / "config.gz"
    boot_config = boot_root / f"config-{release}"
    output.parent.mkdir(parents=True, exist_ok=True)
    if proc_config.is_file():
        with gzip.open(proc_config, "rb") as source:
            output.write_bytes(source.read())
        return output
    if boot_config.is_file():
        output.write_bytes(boot_config.read_bytes())
        return output
    raise FileNotFoundError("running seed kernel config not exposed in /proc/config.gz or /boot/config-<release>")


def capture_lsmod(
    output: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = runner(("lsmod",), check=True, capture_output=True, text=True)
    output.write_text(completed.stdout, encoding="utf-8")
    return output


def capture_seed_build_inputs(
    output_dir: Path,
    *,
    proc_root: Path = Path("/proc"),
    boot_root: Path = Path("/boot"),
    kernel_release: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    config = capture_seed_config(
        output_dir / "seed.config",
        proc_root=proc_root,
        boot_root=boot_root,
        kernel_release=kernel_release,
    )
    lsmod = capture_lsmod(output_dir / "seed.lsmod", runner=runner)
    return config, lsmod


__all__ = ["capture_lsmod", "capture_seed_build_inputs", "capture_seed_config"]
