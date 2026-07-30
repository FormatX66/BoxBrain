# Decision Log

## BB-ADR-042

- **Date:** 2026-07-30
- **Reason:** Relative links to a sibling BrainConnect checkout failed in clean
  BoxBrain worktrees and CI even though the authoritative files were published.
- **Alternatives considered:** Require a fixed sibling checkout; exempt the
  links from validation; copy BrainConnect documents into BoxBrain.
- **Chosen solution:** Link directly to the authoritative files on
  `FormatX66/BrainConnect` `main`.
- **Impact:** Cross-repository links work without local layout assumptions and
  BrainConnect remains the single source of truth.

## BB-ADR-043

- **Date:** 2026-07-30
- **Reason:** BrainConnect's missing documents were present in a clean,
  cumulative twelve-PR stack whose ancestry encoded the implementation order.
- **Alternatives considered:** Link to an immutable historical commit; squash
  the complete stack; recreate the documents manually.
- **Chosen solution:** Validate the cumulative head, then retarget and merge
  each PR bottom-up with exact-head-SHA guards and merge commits.
- **Impact:** All authoritative documents now exist on BrainConnect `main`,
  incremental PR scope remains traceable, and no content was invented.
