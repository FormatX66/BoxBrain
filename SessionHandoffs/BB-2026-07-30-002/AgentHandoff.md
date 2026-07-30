# Agent Handoff

## Current Objective

Preserve the completed BrainConnect alpha baseline and begin only an explicitly
selected post-alpha milestone.

## Tasks

1. Keep the Pi controller inert between bounded experiments.
2. Keep the rotated checkpoint as the exact recovery baseline.
3. Select one post-alpha milestone before adding capabilities.
4. Require structured budgets and verification for any planner work.
5. Retain the fixed scrolling acceptance plan as a regression gate.

## Dependencies

- BrainConnect canonical `main`
- BoxBrain canonical `main`
- Pi controller `10.12.194.1:8000`
- Windows target `10.12.194.9:3389`
- Target UUID `0efb72ab-7b55-481a-914b-f689f427dfef`
- Checkpoint `clean-linked-rotated-2026-07-29`

## Files affected

- BrainConnect deployment script, fixed acceptance plan, tests, and alpha docs
- BoxBrain Hyper-V restore helper, roadmap, project index, and session records

## Required repositories

- `FormatX66/BrainConnect`
- `FormatX66/BoxBrain`

## Verification checklist

- Controller, Flutter, amd64, and arm64 gates pass.
- Exact Pi runtime and upgrade safety gates pass.
- Fixed scroll operations succeed.
- Before/after frame hashes differ.
- Executor is disabled after the run.
- Drop-in, credentials, and temporary runner are absent.
- Rotated checkpoint is restored with the VM off.

## Suggested commit message

`Complete BrainConnect alpha verification`

## Suggested branch

`codex/brainconnect-alpha-finish`

## Potential risks

- A cloud planner could expand authority unless actions remain structured and
  budgeted.
- Shell and clipboard expand data exposure and must remain separate decisions.
- Future Windows line-ending conversion could break remote scripts unless the
  deployment normalization remains covered.

## Estimated completion order

Select milestone, define acceptance contract, implement locally, pass CI,
verify in the disposable lab, clean up, and update the canonical handoff.
