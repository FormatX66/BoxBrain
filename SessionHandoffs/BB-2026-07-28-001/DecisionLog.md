# Decision Log — BB-2026-07-28-001

## BB-ADR-001

- **Date:** 2026-07-28
- **Reason:** The ecosystem needs one searchable operating index without
  duplicating BrainConnect code or technical documentation.
- **Alternatives considered:** Move BrainConnect into a monorepo; copy
  BrainConnect documentation into BoxBrain; keep unrelated standalone folders
  with no common index.
- **Chosen solution:** Use BoxBrain as the knowledge and coordination
  repository while registered implementation repositories remain authoritative.
- **Impact:** Cross-project status and decisions live in BoxBrain. Code and
  detailed project docs remain in their source repositories and are linked.

## BB-ADR-002

- **Date:** 2026-07-28
- **Reason:** Both session files and cumulative logs are required, but repeating
  full entries would violate the non-duplication rule.
- **Alternatives considered:** Duplicate decision and change narratives in both
  places; omit session logs; omit global logs.
- **Chosen solution:** Store the canonical decision and change details in the
  session bundle. Admin logs are chronological indexes that link to them.
- **Impact:** History remains searchable without conflicting copies.

## BB-ADR-003

- **Date:** 2026-07-28
- **Reason:** The requested layout names projects for which no source or
  authoritative description was discovered.
- **Alternatives considered:** Create empty repositories; invent requirements;
  omit the project names.
- **Chosen solution:** Create metadata-only project indexes that explicitly
  state discovery status and unknown fields.
- **Impact:** Names are reserved and discoverable without claiming nonexistent
  implementations.
