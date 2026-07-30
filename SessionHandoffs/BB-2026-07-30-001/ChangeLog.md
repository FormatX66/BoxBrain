# Change Log

## Changed files

- Updated the root `README.md` to index the memory-priority and ChatGPT
  write-boundary documents.
- Updated `Admin/RepositoryIndex.md`, `Admin/Roadmap.md`, and
  `Admin/MasterTODO.md` to use canonical BrainConnect references.
- Updated cross-project architecture and integration documents.
- Updated the BrainConnect and Security project indexes.
- Corrected four historical handoff links without changing their recorded
  decisions.
- Added this complete session bundle and updated the session, decision, and
  change indexes.
- Merged BoxBrain PR #3 at `fbb4ab1` after exact-head verification.
- Extended the existing CI workflow with automatic repository-integrity
  validation for pushes and pull requests targeting `main`.

## Reason

BoxBrain PR #3 was cleanly mergeable but its own validator exposed sibling
repository assumptions and new Markdown files that were not discoverable from
the project index.

## Dependencies

- BrainConnect PRs #1 through #12 are merged into BrainConnect `main`.
- BoxBrain PRs #5 and #2 are merged into BoxBrain `main`.
- BoxBrain PR #3 is merged into BoxBrain `main`.

## Future implications

Cross-repository references should use authoritative repository URLs. New
Markdown files must be linked from a canonical index in the same change. CI
will now enforce both requirements before later pull requests merge.
