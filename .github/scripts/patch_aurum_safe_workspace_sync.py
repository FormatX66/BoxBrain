#!/usr/bin/env python3
"""Wire checkpoint-first behavior into every Aurum Git sync path."""
from pathlib import Path
import re

workspace_path = Path("Projects/AurumPC/aurum_workspace.py")
autonomy_path = Path("Projects/AurumPC/aurum_autonomy.py")
runtime_path = Path("Projects/AurumPC/aurum_runtime_update.py")
build_path = Path("Projects/AurumPC/build-iso.sh")
workspace_text = workspace_path.read_text(encoding="utf-8")
autonomy_text = autonomy_path.read_text(encoding="utf-8")
runtime_text = runtime_path.read_text(encoding="utf-8")
build_text = build_path.read_text(encoding="utf-8")
changed = False

# ---- AurumWorkspace.git_sync -------------------------------------------------
old = '''        changes = self._git("status", "--porcelain=v1").stdout.strip()\n        if changes:\n            raise WorkspaceError("Workspace has local changes; refusing to overwrite or merge them")\n        self._git("fetch", "--prune", "origin", self.branch)\n        self._git("merge", "--ff-only", "FETCH_HEAD")\n        return {"status": "fast-forwarded", **self.git_status()}\n'''

new = '''        branch = self._git("branch", "--show-current").stdout.strip()\n        head = self._git("rev-parse", "HEAD").stdout.strip()\n        changes = [line for line in self._git("status", "--porcelain=v1").stdout.splitlines() if line]\n        checkpoint = None\n        if changes:\n            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())\n            checkpoint = f"aurum-auto-checkpoint-{stamp}"\n            self._git("stash", "push", "-u", "-m", checkpoint)\n            _atomic_json(\n                self.state_dir / "last-workspace-checkpoint.json",\n                {\n                    "schema": "aurum-workspace-checkpoint-v1",\n                    "at": stamp,\n                    "repository": origin,\n                    "branch": branch,\n                    "head_before_sync": head,\n                    "checkpoint": checkpoint,\n                    "changes": changes,\n                    "preserved": True,\n                    "reapplied": False,\n                    "source": "workspace",\n                },\n            )\n        self._git("fetch", "--prune", "origin", self.branch)\n        self._git("merge", "--ff-only", "FETCH_HEAD")\n        result = {"status": "fast-forwarded", **self.git_status()}\n        if checkpoint is not None:\n            result.update(\n                {\n                    "status": "fast-forwarded-with-checkpoint",\n                    "checkpoint": checkpoint,\n                    "checkpoint_preserved": True,\n                    "checkpoint_reapplied": False,\n                }\n            )\n        return result\n'''

current_bug_context = '''        if origin.rstrip("/").removesuffix(".git") != self.repository.removesuffix(".git"):\n            raise WorkspaceError("Workspace origin is outside the Aurum BoxBrain allowlist")\n        changes = [line for line in self._git("status", "--porcelain=v1").stdout.splitlines() if line]\n'''
repaired_context = '''        if origin.rstrip("/").removesuffix(".git") != self.repository.removesuffix(".git"):\n            raise WorkspaceError("Workspace origin is outside the Aurum BoxBrain allowlist")\n        branch = self._git("branch", "--show-current").stdout.strip()\n        head = self._git("rev-parse", "HEAD").stdout.strip()\n        changes = [line for line in self._git("status", "--porcelain=v1").stdout.splitlines() if line]\n'''

if old in workspace_text:
    workspace_text = workspace_text.replace(old, new, 1)
    changed = True
elif current_bug_context in workspace_text:
    workspace_text = workspace_text.replace(current_bug_context, repaired_context, 1)
    changed = True

if 'last-workspace-checkpoint.json' not in workspace_text or 'aurum-auto-checkpoint-' not in workspace_text:
    raise SystemExit("workspace git_sync checkpoint contract is absent")
if 'branch = self._git("branch", "--show-current")' not in workspace_text:
    raise SystemExit("workspace git_sync branch evidence is absent")
if 'head = self._git("rev-parse", "HEAD")' not in workspace_text:
    raise SystemExit("workspace git_sync head evidence is absent")

# ---- AutonomyManager._git_sync ----------------------------------------------
autonomy_method = '''    def _git_sync(self) -> dict[str, Any]:
        if not (self.workspace / ".git").is_dir():
            return {"status": "workspace-unavailable"}
        origin = _run(["git", "remote", "get-url", "origin"], cwd=self.workspace, timeout=20)
        if origin.returncode != 0 or origin.stdout.strip().rstrip("/").removesuffix(".git") != REPOSITORY.removesuffix(".git"):
            return {"status": "refused", "reason": "origin-outside-allowlist"}
        branch = _run(["git", "branch", "--show-current"], cwd=self.workspace, timeout=20)
        if branch.returncode != 0 or branch.stdout.strip() != BRANCH:
            return {"status": "refused", "reason": "branch-outside-allowlist", "branch": branch.stdout.strip()}
        dirty = _run(["git", "status", "--porcelain=v1"], cwd=self.workspace, timeout=30)
        if dirty.returncode != 0:
            return {"status": "failed", "phase": "status", "detail": dirty.stdout.strip()[-1000:]}
        before = self._git_head()
        checkpoint = None
        changes = [line for line in dirty.stdout.splitlines() if line]
        if changes:
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            checkpoint = f"aurum-auto-checkpoint-{stamp}"
            stashed = _run(["git", "stash", "push", "-u", "-m", checkpoint], cwd=self.workspace, timeout=120)
            if stashed.returncode != 0:
                return {
                    "status": "failed",
                    "phase": "checkpoint",
                    "detail": stashed.stdout.strip()[-1500:],
                    "before": before,
                }
            _atomic_json(
                self.state_dir / "last-workspace-checkpoint.json",
                {
                    "schema": "aurum-workspace-checkpoint-v1",
                    "at": stamp,
                    "repository": origin.stdout.strip(),
                    "branch": branch.stdout.strip(),
                    "head_before_sync": before,
                    "checkpoint": checkpoint,
                    "changes": changes,
                    "preserved": True,
                    "reapplied": False,
                    "source": "autonomy",
                },
            )
        fetched = _run(["git", "fetch", "--prune", "origin", BRANCH], cwd=self.workspace, timeout=180)
        if fetched.returncode != 0:
            return {"status": "failed", "phase": "fetch", "detail": fetched.stdout[-1500:], "before": before, "checkpoint": checkpoint}
        fetched_head_result = _run(["git", "rev-parse", "FETCH_HEAD"], cwd=self.workspace, timeout=20)
        fetched_head = fetched_head_result.stdout.strip() if fetched_head_result.returncode == 0 else None
        if not fetched_head:
            return {"status": "failed", "phase": "verify", "reason": "fetched-head-unavailable", "before": before, "checkpoint": checkpoint}
        if before:
            ancestry = _run(["git", "merge-base", "--is-ancestor", before, fetched_head], cwd=self.workspace, timeout=30)
            if ancestry.returncode != 0:
                return {
                    "status": "refused",
                    "phase": "verify",
                    "reason": "non-fast-forward-generation",
                    "before": before,
                    "fetched_head": fetched_head,
                    "checkpoint": checkpoint,
                }
        merged = _run(["git", "merge", "--ff-only", "FETCH_HEAD"], cwd=self.workspace, timeout=120)
        if merged.returncode != 0:
            return {"status": "failed", "phase": "merge", "detail": merged.stdout[-1500:], "before": before, "checkpoint": checkpoint}
        after = self._git_head()
        clean_after = _run(["git", "status", "--porcelain=v1"], cwd=self.workspace, timeout=30)
        verified = bool(after == fetched_head and clean_after.returncode == 0 and not clean_after.stdout.strip())
        result = {
            "status": "ready" if verified else "failed",
            "phase": "verified" if verified else "verify",
            "before": before,
            "head": after,
            "fetched_head": fetched_head,
            "changed": before != after,
            "verification": {
                "passed": verified,
                "exact_origin": True,
                "exact_branch": True,
                "fast_forward_only": True,
                "head_matches_fetched": after == fetched_head,
                "clean": clean_after.returncode == 0 and not clean_after.stdout.strip(),
            },
        }
        if checkpoint is not None:
            result.update(
                {
                    "checkpoint": checkpoint,
                    "checkpoint_preserved": True,
                    "checkpoint_reapplied": False,
                }
            )
        return result
'''

if '"reason": "workspace-dirty"' in autonomy_text or '"source": "autonomy"' not in autonomy_text:
    pattern = re.compile(r'    def _git_sync\(self\) -> dict\[str, Any\]:\n.*?\n    def _subprocess_json\(', re.S)
    replacement = autonomy_method + '\n    def _subprocess_json('
    autonomy_text, count = pattern.subn(replacement, autonomy_text, count=1)
    if count != 1:
        raise SystemExit("could not safely replace AutonomyManager._git_sync")
    changed = True

if '"reason": "workspace-dirty"' in autonomy_text:
    raise SystemExit("autonomy dirty-workspace refusal still present")
if '"source": "autonomy"' not in autonomy_text or 'aurum-auto-checkpoint-' not in autonomy_text:
    raise SystemExit("autonomy checkpoint contract is absent")

# ---- Make the bootstrap helper resident in installed runtime and new ISOs ----
if '    "aurum_sync_recovery.py",\n' not in runtime_text:
    anchor = '    "aurum_runtime_update.py",\n'
    if anchor not in runtime_text:
        raise SystemExit("runtime allowlist anchor is absent")
    runtime_text = runtime_text.replace(anchor, anchor + '    "aurum_sync_recovery.py",\n', 1)
    changed = True

if 'aurum_sync_recovery.py' not in build_text:
    anchor = 'aurum_runtime_update.py aurum_time.py'
    if anchor not in build_text:
        raise SystemExit("ISO runtime-copy anchor is absent")
    build_text = build_text.replace(anchor, 'aurum_runtime_update.py aurum_sync_recovery.py aurum_time.py', 1)
    changed = True

if '    "aurum_sync_recovery.py",\n' not in runtime_text:
    raise SystemExit("runtime does not install aurum_sync_recovery.py")
if 'aurum_sync_recovery.py' not in build_text:
    raise SystemExit("ISO does not bundle aurum_sync_recovery.py")

if changed:
    workspace_path.write_text(workspace_text, encoding="utf-8")
    autonomy_path.write_text(autonomy_text, encoding="utf-8")
    runtime_path.write_text(runtime_text, encoding="utf-8")
    build_path.write_text(build_text, encoding="utf-8")
    print("wired checkpoint-first sync and resident recovery helper")
else:
    print("checkpoint-first sync and resident recovery helper already wired")
