#!/usr/bin/env python3
"""Wire checkpoint-first behavior into AurumWorkspace.git_sync."""
from pathlib import Path

path = Path("Projects/AurumPC/aurum_workspace.py")
text = path.read_text(encoding="utf-8")

old = '''        changes = self._git("status", "--porcelain=v1").stdout.strip()\n        if changes:\n            raise WorkspaceError("Workspace has local changes; refusing to overwrite or merge them")\n        self._git("fetch", "--prune", "origin", self.branch)\n        self._git("merge", "--ff-only", "FETCH_HEAD")\n        return {"status": "fast-forwarded", **self.git_status()}\n'''

new = '''        branch = self._git("branch", "--show-current").stdout.strip()\n        head = self._git("rev-parse", "HEAD").stdout.strip()\n        changes = [line for line in self._git("status", "--porcelain=v1").stdout.splitlines() if line]\n        checkpoint = None\n        if changes:\n            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())\n            checkpoint = f"aurum-auto-checkpoint-{stamp}"\n            self._git("stash", "push", "-u", "-m", checkpoint)\n            _atomic_json(\n                self.state_dir / "last-workspace-checkpoint.json",\n                {\n                    "schema": "aurum-workspace-checkpoint-v1",\n                    "at": stamp,\n                    "repository": origin,\n                    "branch": branch,\n                    "head_before_sync": head,\n                    "checkpoint": checkpoint,\n                    "changes": changes,\n                    "preserved": True,\n                    "reapplied": False,\n                },\n            )\n        self._git("fetch", "--prune", "origin", self.branch)\n        self._git("merge", "--ff-only", "FETCH_HEAD")\n        result = {"status": "fast-forwarded", **self.git_status()}\n        if checkpoint is not None:\n            result.update(\n                {\n                    "status": "fast-forwarded-with-checkpoint",\n                    "checkpoint": checkpoint,\n                    "checkpoint_preserved": True,\n                    "checkpoint_reapplied": False,\n                }\n            )\n        return result\n'''

legacy_context = '''        if origin.rstrip("/").removesuffix(".git") != self.repository.removesuffix(".git"):\n            raise WorkspaceError("Workspace origin is outside the Aurum BoxBrain allowlist")\n        changes = self._git("status", "--porcelain=v1").stdout.strip()\n'''
repaired_context = '''        if origin.rstrip("/").removesuffix(".git") != self.repository.removesuffix(".git"):\n            raise WorkspaceError("Workspace origin is outside the Aurum BoxBrain allowlist")\n        branch = self._git("branch", "--show-current").stdout.strip()\n        head = self._git("rev-parse", "HEAD").stdout.strip()\n        changes = [line for line in self._git("status", "--porcelain=v1").stdout.splitlines() if line]\n'''
current_bug_context = '''        if origin.rstrip("/").removesuffix(".git") != self.repository.removesuffix(".git"):\n            raise WorkspaceError("Workspace origin is outside the Aurum BoxBrain allowlist")\n        changes = [line for line in self._git("status", "--porcelain=v1").stdout.splitlines() if line]\n'''

if old in text:
    text = text.replace(old, new, 1)
elif current_bug_context in text:
    text = text.replace(current_bug_context, repaired_context, 1)
elif repaired_context in text and 'last-workspace-checkpoint.json' in text:
    print("safe workspace sync already wired and repaired")
    raise SystemExit(0)
elif legacy_context in text:
    raise SystemExit("legacy context found but expected refusal block shape changed")
else:
    raise SystemExit("could not identify a safe Aurum git_sync patch point")

path.write_text(text, encoding="utf-8")
print("wired checkpoint-first workspace sync with branch/head evidence")
