from __future__ import annotations

from dataclasses import dataclass
import fnmatch
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ModuleAliasMatch:
    modalias: str
    modules: tuple[str, ...]


def parse_modules_alias(path: Path) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3 or parts[0] != "alias":
            continue
        entries.append((parts[1], parts[2]))
    return tuple(entries)


def resolve_modalias(modalias: str, aliases: Iterable[tuple[str, str]]) -> ModuleAliasMatch:
    modules = tuple(sorted({module for pattern, module in aliases if fnmatch.fnmatchcase(modalias, pattern)}))
    return ModuleAliasMatch(modalias=modalias, modules=modules)


def resolve_modaliases(modaliases: Iterable[str], modules_alias_path: Path) -> tuple[ModuleAliasMatch, ...]:
    aliases = parse_modules_alias(modules_alias_path)
    return tuple(resolve_modalias(value, aliases) for value in sorted(set(modaliases)))


__all__ = ["ModuleAliasMatch", "parse_modules_alias", "resolve_modalias", "resolve_modaliases"]
