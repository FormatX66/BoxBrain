# Change Log

## Changed files

### BrainConnect

- Tightened the pointer-scroll controller schema and API tests.
- Added dashboard coordinates, wheel limits, payload generation, and widget
  coverage.
- Added native scroll parsing, signed wheel encoding, move-plus-scroll
  delivery, protocol tests, identity-negative coverage, and provenance.
- Added scroll support to the bounded Pi experiment runner and its tests.
- Updated the plugin manifest, native project version, protocol, deployment,
  product, development, security, and roadmap documentation.

### BoxBrain

- Updated the BrainConnect project, roadmap, repository, task, decision,
  change, and session indexes.
- Added session `BB-2026-07-29-012`.

## Reason

Implement the operator-approved lowest-exposure native capability while
preserving system-intensive build and live verification for nightshift.

## Dependencies

- Existing pinned RDP identity and target-bound credential boundary
- Existing slow-path input and standard target-user session handling
- RDP vertical/horizontal wheel flags and signed nine-bit rotation field
- Existing bounded frame observation for independent proof

## Future implications

- Shell and clipboard remain separate capability expansions.
- Scroll promotion now depends on full native, Pi-runtime, and before/after
  frame gates.
- The daytime/nightshift division remains the operating model.
