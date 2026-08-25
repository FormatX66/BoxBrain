# Aurum State Authority and Memory Hierarchy

## Purpose

Aurum must not depend on ChatGPT conversation memory for build continuity, architecture, requirements, or recovery. Chat memory is useful context, but it is not authoritative project state.

## Authority order

### 1. GitHub / project files — authoritative durable state

Repository files, committed architecture, build manifests, requirements, tests, issue state, checkpoints, and version history are the canonical record for Aurum.

If a chat memory, model summary, local cache, or verbal description conflicts with committed project state, the committed project state wins unless an explicit newer change is intentionally committed.

Important design decisions discovered in conversation should be converted into repository artifacts rather than existing only in chat.

### 2. Aurum local operational state — authoritative runtime state

Aurum should maintain its own machine-readable operational state for active execution, including:

- current build graph and atomic jobs
- completed, runnable, blocked, failed, and retrying work
- dependency state
- current hardware/software fingerprints
- generated artifacts and their hashes
- validation/test results
- checkpoints and resumable execution position
- active hypotheses/confidence where applicable
- recovery/fallback state
- provenance linking operational state back to committed requirements

Operational state should be persisted locally and checkpointed frequently enough that Aurum can restart without reconstructing its state from a conversation.

Where practical, durable summaries/checkpoints that define project behavior should be synchronized into versioned project artifacts.

The local checkpoint writer is `Admin/checkpoint_aurum_runtime.py`. By default it atomically writes `data/aurum/runtime-checkpoint.json`, which is intentionally ignored by Git. It starts from the durable repository reconstruction, then adds local jobs, resumable positions, hardware/software fingerprints, hypotheses, and local artifact references supplied by the runtime. Stored checkpoint state can resume work, but it cannot grant destructive authority, promote a candidate, or mutate LKG; those boundaries always require fresh live evidence.

Example local checkpoint refresh:

`python Admin/checkpoint_aurum_runtime.py`

A runtime may pass a JSON overlay with `--runtime-overlay <path>` to persist active jobs and local fingerprints without moving those ephemeral details into Git.

### 3. ChatGPT / external AI memory — supplemental context only

Conversation memory, summaries, model context, and other external AI memory may help interpret intent or accelerate work, but they must never be the only copy of:

- a requirement
- a build decision
- a queued task
- a test result
- a hardware characterization result
- a recovery instruction
- an architecture rule
- a credential or secret

Aurum should assume external AI memory can be missing, stale, unavailable, or contradictory.

## Reconciliation rule

When sources disagree:

1. Verify the current repository/project state.
2. Verify Aurum's current runtime checkpoint and hardware/software fingerprint.
3. Treat chat/external memory as a hint, not a fact.
4. Preserve conflicting evidence rather than silently overwriting it.
5. Commit intentional architecture/requirement changes so the durable source of truth advances explicitly.

## Continuity rule

Aurum should be able to stop, restart, move between model providers, lose a conversation, or lose all external chat memory and still answer:

`What am I building? -> What is already done? -> What is running? -> What is blocked? -> What evidence supports this state? -> What should execute next?`

without asking a human to reconstruct prior conversations.

The repository carries an executable continuity proof at `Admin/reconstruct_aurum_state.py`. It reconstructs those answers from the committed completion plan, verified Tiny Seed handoff, current zero-authority physical preflight, and Future Branch state only. It deliberately does not infer a live process, destructive authority, physical proof, or LKG mutation from stored snapshots. Canonical release provenance disagreement or broken gate dependencies fail closed. The proof is part of repository CI through `Admin.tests.test_reconstruct_aurum_state`.

A direct operator or recovery check is:

`python Admin/reconstruct_aurum_state.py`

The emitted `aurum-restart-reconstruction-v1` object is a reconstruction artifact, not an authorization token. Any human-only, physical, destructive, or time-sensitive boundary still requires fresh live evidence and Action Ownership checks.

The local operational layer is separately exercised by `Admin.tests.test_checkpoint_aurum_runtime`, including atomic persistence, resumable-job capture, invalid-state refusal, duplicate-job refusal, and proof that an overlay cannot smuggle destructive authority or LKG mutation into a checkpoint.

## Design consequence

ChatGPT memory failures are non-critical unless they reveal that important state exists only in chat. The fix for that condition is not to make chat memory authoritative; it is to move the missing state into Aurum's durable project/runtime stores.

## Relation to autonomous builds

This hierarchy applies to all Aurum self-building systems, including Autonomous Driver Synthesis. Generated drivers, hardware models, confidence records, source provenance, test results, and rollback/fallback information must be preserved in Aurum/project state rather than relying on conversational memory.
