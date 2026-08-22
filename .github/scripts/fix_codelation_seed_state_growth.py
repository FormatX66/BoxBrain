#!/usr/bin/env python3
"""Make Codelation state evolution non-blocking for the Aurum seed lifecycle."""
from pathlib import Path

path = Path("Projects/Codelation/seed/codelation_seed.py")
text = path.read_text(encoding="utf-8")

marker = '''\ndef short(identity: bytes | None) -> str:\n    return "none" if identity is None else identity.hex()[:12]\n'''
addition = '''\ndef _load_runtime_seed(path: Path) -> tuple[SeedGraph, dict[str, str] | None]:\n    """Load seed state without allowing an old/corrupt model to gate growth.\n\n    SeedGraph.load remains strict for diagnostics and tests.  The running seed\n    preserves incompatible state beside the original path, starts a compatible\n    graph, and emits a receipt so a state-model experiment can never stop the\n    Aurum generation lifecycle.\n    """\n    try:\n        return SeedGraph.load(path), None\n    except (OSError, ValueError, struct.error) as exc:\n        if not path.exists():\n            return SeedGraph(), {\n                "status": "recovered-fresh",\n                "reason": f"{type(exc).__name__}:{exc}",\n                "preserved": "none",\n            }\n        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())\n        preserved = path.with_name(f"{path.name}.preserved-{stamp}")\n        counter = 1\n        while preserved.exists():\n            preserved = path.with_name(f"{path.name}.preserved-{stamp}-{counter}")\n            counter += 1\n        try:\n            os.replace(path, preserved)\n        except OSError as preserve_exc:\n            return SeedGraph(), {\n                "status": "recovered-in-memory",\n                "reason": f"{type(exc).__name__}:{exc}",\n                "preserve_error": f"{type(preserve_exc).__name__}:{preserve_exc}",\n                "preserved": "failed",\n            }\n        return SeedGraph(), {\n            "status": "recovered-compatible-state",\n            "reason": f"{type(exc).__name__}:{exc}",\n            "preserved": str(preserved),\n        }\n\n\ndef short(identity: bytes | None) -> str:\n    return "none" if identity is None else identity.hex()[:12]\n'''

if "def _load_runtime_seed(" not in text:
    if marker not in text:
        raise SystemExit("seed insertion marker missing")
    text = text.replace(marker, addition, 1)

old = "    graph = SeedGraph.load(args.model)\n"
new = '''    graph, recovery = _load_runtime_seed(args.model)\n    if recovery is not None:\n        print("AURUM_SEED_STATE_RECOVERY " + json.dumps(recovery, sort_keys=True))\n'''
if new not in text:
    if old not in text:
        raise SystemExit("runtime load marker missing")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Codelation seed-state evolution is now non-blocking")
