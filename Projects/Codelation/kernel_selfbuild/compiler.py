"""Out-of-tree Linux kernel compiler with bounded artifact provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable


_ARCH_TO_KBUILD = {"x86_64": "x86", "arm64": "arm64"}
_ARCH_IMAGE = {
    "x86_64": "arch/x86/boot/bzImage",
    "arm64": "arch/arm64/boot/Image",
}
_VERSION_FIELD = re.compile(
    r"^(VERSION|PATCHLEVEL|SUBLEVEL|EXTRAVERSION)\s*=\s*(.*?)\s*$"
)


@dataclass(frozen=True)
class KernelCompileRequest:
    architecture: str
    source_dir: Path
    output_dir: Path
    stage_dir: Path
    base_config: Path
    jobs: int = 1
    build_modules: bool = False
    extra_build_targets: tuple[str, ...] = ()
    lsmod_file: Path | None = None
    cross_compile: str | None = None


@dataclass(frozen=True)
class KernelArtifactManifest:
    schema: str
    architecture: str
    kbuild_arch: str
    kernel_version: str
    image_relative_path: str
    image_sha256: str
    config_sha256: str
    build_modules: bool
    module_stage: str | None
    source_identity: str
    commands: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identity(source_dir: Path) -> str:
    digest = hashlib.sha256(b"AURUM-KERNEL-SOURCE-1\0")
    for name in ("Makefile", "Kconfig", "scripts/setlocalversion"):
        path = source_dir / name
        digest.update(name.encode("utf-8") + b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _kernel_version(source_dir: Path) -> str:
    fields: dict[str, str] = {}
    for line in (source_dir / "Makefile").read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        match = _VERSION_FIELD.match(line)
        if match:
            fields[match.group(1)] = match.group(2)
    required = ("VERSION", "PATCHLEVEL", "SUBLEVEL")
    if any(not fields.get(name) for name in required):
        raise ValueError("kernel source Makefile does not expose a complete version")
    return (
        f"{fields['VERSION']}.{fields['PATCHLEVEL']}.{fields['SUBLEVEL']}"
        f"{fields.get('EXTRAVERSION', '')}"
    )


def validate_compile_request(request: KernelCompileRequest) -> None:
    if request.architecture not in _ARCH_TO_KBUILD:
        raise ValueError(f"unsupported architecture: {request.architecture}")
    if request.jobs < 1 or request.jobs > 256:
        raise ValueError("jobs must be between 1 and 256")
    if not isinstance(request.build_modules, bool):
        raise TypeError("build_modules must be a bool")
    if any(
        not target
        or target.startswith("-")
        or not re.fullmatch(r"[A-Za-z0-9_./+-]+", target)
        for target in request.extra_build_targets
    ):
        raise ValueError("extra_build_targets contains an invalid make target")
    source = request.source_dir.resolve()
    output = request.output_dir.resolve()
    stage = request.stage_dir.resolve()
    if not (source / "Makefile").is_file() or not (source / "Kconfig").is_file():
        raise ValueError("source_dir is not a Linux kernel source tree")
    if not request.base_config.is_file():
        raise ValueError("base_config is missing")
    if output == source or source in output.parents:
        raise ValueError("output_dir must not be inside the kernel source tree")
    if stage == source or source in stage.parents:
        raise ValueError("stage_dir must not be inside the kernel source tree")
    if output == stage:
        raise ValueError("output_dir and stage_dir must be different")
    if request.lsmod_file is not None and not request.lsmod_file.is_file():
        raise ValueError("lsmod_file is missing")


def compile_commands(request: KernelCompileRequest) -> tuple[tuple[str, ...], ...]:
    validate_compile_request(request)
    arch = _ARCH_TO_KBUILD[request.architecture]
    common = (
        "make",
        "-C",
        str(request.source_dir.resolve()),
        f"O={request.output_dir.resolve()}",
        f"ARCH={arch}",
    )
    if request.cross_compile:
        common += (f"CROSS_COMPILE={request.cross_compile}",)
    commands: list[tuple[str, ...]] = [common + ("olddefconfig",)]
    if request.lsmod_file is not None:
        commands.append(
            common + (f"LSMOD={request.lsmod_file.resolve()}", "localmodconfig")
        )
        commands.append(common + ("olddefconfig",))
    image_target = _ARCH_IMAGE[request.architecture].split("/")[-1]
    targets = (image_target, *request.extra_build_targets)
    if request.build_modules:
        targets += ("modules",)
    commands.append(common + (f"-j{request.jobs}", *targets))
    if request.build_modules:
        commands.append(
            common
            + (
                f"-j{request.jobs}",
                "modules_install",
                f"INSTALL_MOD_PATH={request.stage_dir.resolve()}",
            )
        )
    return tuple(commands)


def compile_kernel(
    request: KernelCompileRequest,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> KernelArtifactManifest:
    validate_compile_request(request)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    request.stage_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(request.base_config, request.output_dir / ".config")
    commands = compile_commands(request)
    for command in commands:
        runner(command, check=True)

    image_relative = _ARCH_IMAGE[request.architecture]
    image_path = request.output_dir / image_relative
    config_path = request.output_dir / ".config"
    if not image_path.is_file():
        raise RuntimeError(f"kernel image missing after build: {image_path}")
    if not config_path.is_file():
        raise RuntimeError("final kernel config missing after build")

    manifest = KernelArtifactManifest(
        schema="aurum-machine-kernel-artifact-v1",
        architecture=request.architecture,
        kbuild_arch=_ARCH_TO_KBUILD[request.architecture],
        kernel_version=_kernel_version(request.source_dir.resolve()),
        image_relative_path=image_relative,
        image_sha256=_sha256(image_path),
        config_sha256=_sha256(config_path),
        build_modules=request.build_modules,
        module_stage=(
            str(request.stage_dir.resolve()) if request.build_modules else None
        ),
        source_identity=_source_identity(request.source_dir.resolve()),
        commands=commands,
    )
    (request.output_dir / "aurum-kernel-manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "KernelArtifactManifest",
    "KernelCompileRequest",
    "compile_commands",
    "compile_kernel",
    "validate_compile_request",
]
