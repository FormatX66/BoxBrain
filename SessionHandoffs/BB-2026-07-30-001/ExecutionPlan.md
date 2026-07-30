# Execution Plan

1. Stage the reviewed integration repair and session records.
2. Commit the merge with `docs: reconcile canonical BrainConnect integration`.
3. Push the exact commit to `codex/repository-organization`.
4. Re-read BoxBrain PR #3 metadata, checks, comments, base, and head SHA.
5. Mark PR #3 ready only if it remains clean.
6. Merge PR #3 into BoxBrain `main` with the reviewed head SHA.
7. Fast-forward the local BoxBrain checkout without touching unrelated
   untracked files.
8. Run the repository validator and focused regression checks on final
   `main`.
