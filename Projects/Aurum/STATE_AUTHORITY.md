# Aurum State Authority and Memory Hierarchy

## Purpose

Aurum must not depend on ChatGPT conversation memory for build continuity, architecture, requirements, or recovery. Chat memory is useful context, but it is not authoritative project state.

## Authority order

### 1. GitHub / project files — authoritative durable state

Repository files, committed architecture, build manifests, requirements, tests, issue state, checkpoints, and version history are the canonical record for Aurum.

If a chat memory, model summary, local cache, or verbal description conflicts with committed project state, the committed project state wins unless an explicit newer change is intentionally committed.

Important design decisions discovered in conversation should be converted into repository artifacts rather than existing only in chat.

### 2. Aurum local operational state — authoritative runtime state

Aurum maintains machine-readable operational state for active execution, including:

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

Operational state must be persisted locally and checkpointed frequently enough that Aurum can restart without reconstructing its state from a conversation.

Where practical, durable summaries/checkpoints that define project behavior should be synchronized into versioned project artifacts.

#### Production controller: Aurum Farmer

On a node where **Aurum Farmer is deployed as the persistent controller**, Farmer's SQLite WAL ledger plus its local signing key is the production local operational-state authority. The ledger owns durable jobs, Future Branch candidates, attempts, leases, retries/recovery, human boundaries, append-only signed evidence/event records, sealed receipts, and scoped Last Known Good records.

This is an explicit architecture decision: **do not maintain Farmer and `runtime-checkpoint.json` as two peer authorities.** Duplicate writable authorities would create a split-brain failure mode more dangerous than losing a cache.

The production order inside the local operational layer is therefore:

1. a live Farmer ledger whose event chain and signing material validate;
2. a compatibility checkpoint derived from that Farmer ledger;
3. the generic local checkpoint only when Farmer is not the active controller for that node.

If a Farmer-derived compatibility checkpoint disagrees with the validating Farmer ledger, the Farmer ledger wins and the compatibility snapshot must be regenerated. If the Farmer ledger cannot be validated, fail closed rather than silently falling back to a stale peer snapshot for side-effecting work.

The deployed Windows proof in `Projects/AurumFarmer/Deploy/latest-windows-runtime-proof.json` demonstrates a real process/service boundary: Farmer was stopped, a durable job was queued, the supervisor restarted after the old leader lease expired, and the same ledger job completed with a sealed receipt while the event chain remained valid. That is deployed operational restart/resume evidence for the production local state implementation. It does not grant destructive authority or imply unrelated physical proof.

#### Generic compatibility/fallback checkpoint

`Admin/checkpoint_aurum_runtime.py` writes the repository-ignored `data/aurum/runtime-checkpoint.json`. It starts from the durable repository reconstruction, then adds local jobs, resumable positions, hardware/software fingerprints, hypotheses, and local artifact references supplied by the runtime. Stored checkpoint state can resume work, but it cannot grant destructive authority, promote a candidate, or mutate LKG; those boundaries always require fresh live evidence.

On non-Farmer nodes this file is the bounded generic local operational checkpoint. On Farmer-controlled nodes it is a **compatibility/reconstruction projection only**, not a second authoritative scheduler state.

`Admin/checkpoint_farmer_runtime.py` is the fail-closed bridge from Farmer into the generic checkpoint contract. It requires the Farmer ledger and signing key to already exist, verifies the append-only Farmer event chain, maps durable Farmer job states into the generic resumable-state vocabulary, and emits a zero-authority compatibility snapshot. It refuses a missing signing key instead of creating replacement signing material.

Example generic checkpoint refresh on a non-Farmer node:

`python Admin/checkpoint_aurum_runtime.py`

Example Farmer compatibility projection:

`python Admin/checkpoint_farmer_runtime.py --ledger <farmer-ledger.sqlite3>`

A runtime may pass a JSON overlay to the generic writer with `--runtime-overlay <path>` only when that runtime is itself the intended local operational source. A Farmer-controlled node should project from Farmer rather than hand-maintain an independent overlay.

The restart-side companion is `Admin/resume_aurum_runtime.py`. It first reconstructs current canonical repository truth, then accepts a local checkpoint only if its durable-state digest, release provenance, canonical next gate, schema, freshness, and zero-authority contract still match. It restores checkpointed running/retrying/runnable/blocked/failed job evidence and resume hints without claiming those processes are currently live. Repository-head drift is surfaced for job revalidation rather than silently treated as proof that old work is still executing.

Example restart reconstruction using the generic compatibility/fallback layer:

`python Admin/resume_aurum_runtime.py`

A stale, tampered, incomplete, provenance-mismatched, or authority-bearing checkpoint is refused. A valid checkpoint is still evidence only: every resumed side-effecting job must re-observe current dependencies and authority before execution.

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
2. If Farmer is the active controller, verify Farmer's ledger, signing material, event chain, and current leases/jobs.
3. Otherwise verify the generic local runtime checkpoint and current hardware/software fingerprint.
4. Treat derived Farmer compatibility checkpoints as caches/reconstruction artifacts, not peer truth.
5. Treat chat/external memory as a hint, not a fact.
6. Preserve conflicting evidence rather than silently overwriting it.
7. Commit intentional architecture/requirement changes so the durable source of truth advances explicitly.

## Continuity rule

Aurum should be able to stop, restart, move between model providers, lose a conversation, or lose all external chat memory and still answer:

`What am I building? -> What is already done? -> What is running? -> What is blocked? -> What evidence supports this state? -> What should execute next?`

without asking a human to reconstruct prior conversations.

The repository carries an executable continuity proof at `Admin/reconstruct_aurum_state.py`. It reconstructs those answers from the committed completion plan, verified Tiny Seed handoff, current zero-authority physical preflight, and Future Branch state only. It deliberately does not infer a live process, destructive authority, physical proof, or LKG mutation from stored snapshots. Canonical release provenance disagreement or broken gate dependencies fail closed. The proof is part of repository CI through `Admin.tests.test_reconstruct_aurum_state`.

A direct operator or recovery check is:

`python Admin/reconstruct_aurum_state.py`

The emitted `aurum-restart-reconstruction-v1` object is a reconstruction artifact, not an authorization token. Any human-only, physical, destructive, or time-sensitive boundary still requires fresh live evidence and Action Ownership checks.

The generic local operational layer is exercised in both directions. `Admin.tests.test_checkpoint_aurum_runtime` covers atomic persistence, resumable-job capture, invalid-state refusal, duplicate-job refusal, explicit source metadata, and proof that an overlay cannot smuggle destructive authority or LKG mutation into a checkpoint. `Admin.tests.test_checkpoint_farmer_runtime` covers Farmer-to-generic projection, preserved zero authority, job-state projection, validated event-chain provenance, and missing-signing-key refusal. `Admin.tests.test_resume_aurum_runtime` covers the restart-side round trip: restoring checkpointed runtime evidence, refusing stale/tampered/provenance-mismatched checkpoints, refusing authority-bearing checkpoints, and preserving the rule that checkpointed jobs are not claimed live until re-observed.

Implementation/CI proof remains distinct from deployed proof. The generic checkpoint/resume primitive has process-boundary CI proof. Farmer additionally has a real deployed process-boundary restart/resume receipt on the self-hosted Windows node. That deployed receipt proves local operational continuity for Farmer; it does not infer any Tiny Seed physical boot, Guardian rollback, destructive authority, or candidate promotion.

## Design consequence

ChatGPT memory failures are non-critical unless they reveal that important state exists only in chat. The fix for that condition is not to make chat memory authoritative; it is to move the missing state into Aurum's durable project/runtime stores.

Likewise, adding another state file is not automatically safer. Aurum should prefer **one writable authority with many verifiable projections** over multiple competing writable authorities.

## Relation to autonomous builds

This hierarchy applies to all Aurum self-building systems, including Autonomous Driver Synthesis. Generated drivers, hardware models, confidence records, source provenance, test results, and rollback/fallback information must be preserved in Aurum/project state rather than relying on conversational memory.
