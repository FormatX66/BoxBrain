#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

SCHEMA = "aurum-llm-corpus-v1"
DEFAULT_SOURCES = (
    "Projects/AurumLLM/README.md",
    "Projects/AurumLLM/system.txt",
    "Projects/AurumLLM/seed-model.json",
    "Projects/AurumPC/README.md",
    "Projects/AurumPC/AUTONOMY_ENVELOPE.md",
    "Projects/AurumPC/CODELATION_CAPABILITY_GRAPH.md",
    "Projects/AurumPC/GENERATION_NAMING.md",
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|secret)\s*[=:]\s*\S+"),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def chunks(text: str, limit: int = 3200) -> Iterable[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        if len(paragraph) > limit:
            if current:
                yield "\n\n".join(current)
                current, size = [], 0
            for start in range(0, len(paragraph), limit):
                piece = paragraph[start : start + limit].strip()
                if piece:
                    yield piece
            continue
        addition = len(paragraph) + (2 if current else 0)
        if current and size + addition > limit:
            yield "\n\n".join(current)
            current, size = [], 0
        current.append(paragraph)
        size += addition
    if current:
        yield "\n\n".join(current)


def build(repo: Path, output: Path, manifest_path: Path, sources: Iterable[str]) -> dict:
    records: list[dict] = []
    manifest_sources: list[dict] = []
    rejected: list[dict] = []
    for relative in sources:
        path = (repo / relative).resolve()
        try:
            path.relative_to(repo.resolve())
        except ValueError:
            rejected.append({"source": relative, "reason": "path-escape"})
            continue
        if not path.is_file():
            rejected.append({"source": relative, "reason": "missing"})
            continue
        raw = path.read_bytes()
        text = clean_text(raw.decode("utf-8", "replace"))
        if contains_secret(text):
            rejected.append({"source": relative, "reason": "secret-pattern"})
            continue
        source_sha = sha256_bytes(raw)
        count = 0
        for index, piece in enumerate(chunks(text)):
            if len(piece) < 80:
                continue
            framed = (
                "<aurum_reference>\n"
                f"source: {relative}\n"
                f"source_sha256: {source_sha}\n"
                "origin: aurum-project-owned\n\n"
                f"{piece}\n"
                "</aurum_reference>"
            )
            records.append(
                {
                    "schema": SCHEMA,
                    "text": framed,
                    "source": relative,
                    "source_sha256": source_sha,
                    "chunk": index,
                    "origin": "aurum-project-owned",
                }
            )
            count += 1
        manifest_sources.append(
            {"source": relative, "sha256": source_sha, "records": count, "origin": "aurum-project-owned"}
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    output.write_text(payload, encoding="utf-8")
    manifest = {
        "schema": SCHEMA,
        "records": len(records),
        "corpus_sha256": sha256_bytes(payload.encode("utf-8")),
        "sources": manifest_sources,
        "rejected": rejected,
        "contains_openai_output": False,
        "contains_user_conversation": False,
        "promotion_authorized": False,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a provenance-gated Aurum LLM corpus")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist/aurum-llm-training/corpus.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("dist/aurum-llm-training/corpus-manifest.json"))
    parser.add_argument("--source", action="append", dest="sources")
    args = parser.parse_args()
    manifest = build(args.repo.resolve(), args.output, args.manifest, args.sources or DEFAULT_SOURCES)
    print(json.dumps(manifest, sort_keys=True))
    return 0 if manifest["records"] > 0 and not manifest["rejected"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
