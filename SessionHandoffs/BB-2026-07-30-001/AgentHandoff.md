# Agent Handoff

## Current objective

Maintain the integrated BoxBrain and BrainConnect repositories while routing
the next work through the canonical priority and non-duplication rules.

## Tasks

1. Confirm project owners and ecosystem priority ordering.
2. Clarify Arkmatx's purpose and locate any existing assets before creating
   documentation or code.
3. Define release and archive procedures.
4. Define the Docker, Raspberry Pi, VM, and cloud deployment matrix.
5. Keep the existing CI and repository validator synchronized.

## Dependencies

- BoxBrain `main` at or after `fbb4ab1`.
- BrainConnect `main` at or after `a431665`.
- Authenticated access to `FormatX66/BoxBrain` and
  `FormatX66/BrainConnect`.

## Files affected

- `README.md`
- `Admin/`
- `Architecture/`
- `Projects/`
- selected historical `SessionHandoffs/`
- `SessionHandoffs/BB-2026-07-30-001/`
- `.github/workflows/ci.yml`

## Required repositories

- `FormatX66/BoxBrain`
- `FormatX66/BrainConnect`

## Verification checklist

- BoxBrain repository validator passes.
- Repository-validator unit test passes.
- Controller tests pass.
- Kali Pi edge-agent tests pass.
- Changed PowerShell scripts parse.
- Repository-integrity CI runs for pushes and pull requests to `main`.
- No unresolved integration PRs remain.

## Suggested commit message

`ci: enforce canonical repository validation`

## Suggested branch

`codex/integration-closeout`

## Potential risks

- A future BrainConnect documentation rename could break an absolute link.
- Squashing the historical stacked BrainConnect PRs would have obscured their
  ancestry; merge commits were used instead.
- BoxBrain PR #3 contains operational history as well as repository structure,
  so repository validation is required after every integration.

## Estimated completion order

Confirm ownership, define Arkmatx, document release/archive policy, then define
the deployment matrix.
