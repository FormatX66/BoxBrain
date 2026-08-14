from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import subprocess
from typing import Callable


@dataclass(frozen=True)
class ExternalModuleBuildResult:
    module_dir: str
    kernel_build_dir: str
    ko_files: tuple[str, ...]
    sha256: tuple[tuple[str, str], ...]
    loaded: bool = False
    installed_to_running_kernel: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_external_module(
    *,
    kernel_build_dir: Path,
    module_dir: Path,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> ExternalModuleBuildResult:
    kernel = kernel_build_dir.resolve()
    module = module_dir.resolve()
    if not kernel.is_dir() or not (kernel / "Makefile").is_file():
        raise ValueError("kernel_build_dir is not prepared for kbuild")
    if not module.is_dir() or not ((module / "Makefile").is_file() or (module / "Kbuild").is_file()):
        raise ValueError("module_dir requires a Makefile or Kbuild file")

    # Build only. Loading and installation into the running OS are separate approval gates.
    runner(("make", "-C", str(kernel), f"M={module}", "modules"), check=True)
    modules = tuple(sorted(module.glob("*.ko")))
    if not modules:
        raise RuntimeError("external module build produced no .ko files")
    return ExternalModuleBuildResult(
        module_dir=str(module),
        kernel_build_dir=str(kernel),
        ko_files=tuple(str(path) for path in modules),
        sha256=tuple((path.name, _sha256(path)) for path in modules),
    )


__all__ = ["ExternalModuleBuildResult", "build_external_module"]
