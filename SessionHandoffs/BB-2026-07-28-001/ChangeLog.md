# Change Log — BB-2026-07-28-001

## Added

- Root navigation and source-of-truth policy in `README.md`.
- Admin repository, roadmap, TODO, decision, change, and session indexes.
- System, agent, data-flow, and integration architecture records.
- Eight project indexes and ten agent role records.
- Canonical repository organization prompt and template guidance.
- Session handoff bundle and archive policy.
- `Admin/validate_repository.py` for required-file, local-link, and orphan
  Markdown validation.

## Reason

Establish a coherent, searchable BoxBrain control repository while preserving
BrainConnect as an independent canonical implementation repository.

## Dependencies

- Existing BrainConnect repository at revision `1c6c926`
- Python standard library for repository validation

## Future implications

- Project changes must update their BoxBrain index and the next handoff.
- Repository movement requires updating the registry and relative links.
- Global decision and change files remain indexes, not duplicate narratives.
- Planned project folders must remain metadata-only until source is confirmed.
