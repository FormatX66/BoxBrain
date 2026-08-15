# Codelation

Codelation is an experimental machine-native computation model for BoxBrain.
Instead of generating and executing human-readable source code, a seed observes
opaque states, records transitions, predicts the next state, and strengthens or
weakens relationships based on what actually happens.

## First seed

The first seed is a bootstrap experiment, not the final Codelation runtime. It
is implemented in Python only so it can run safely on a Raspberry Pi today.
The learned model is stored as a compact binary transition graph. It contains
no Python, shell commands, prompts, or executable instructions.

The seed converts observations into fixed-size state identities, records
transitions, predicts the strongest next state, validates predictions, and
persists relationships for later sessions. The human-readable layer is
diagnostic only; it summarizes the graph without becoming the graph.

## Safety boundary

Version 0 does not execute predicted states, modify the host, access the
network, or interpret observations as commands. It only learns and reports
state relationships. Any future actuation layer must be separately designed,
permission-gated, and reversible.

The Aurum dialogue layer is separate from that passive transition model. Its
replaceable mind is declarative JSON rather than executable code. A fixed
supervisor owns network access, credentials, validation, evidence, rollback,
and the allowed-action list. A self-built mind may change Aurum's conversational
voice and self-description, but cannot add shell, service, persistence, or host
actuation authority.

Codelation is not a deployment or liveness gate for Aurum. When an operator has
already installed and started an Aurum gold seed, that observed runtime is the
preserved baseline. A newer dialogue/live-graph layer must reconcile into it
without re-seeding, replacing an opaque seed file, or rejecting operator-approved
services merely because they exist.

## Raspberry Pi quick start

```bash
cd Projects/Codelation
python3 seed/codelation_seed.py observe --model seed.bin boot
python3 seed/codelation_seed.py observe --model seed.bin ready
python3 seed/codelation_seed.py observe --model seed.bin boot
python3 seed/codelation_seed.py predict --model seed.bin boot
python3 seed/codelation_seed.py summary --model seed.bin
```

Run verification with `python3 -m unittest discover -s tests -v`.

From an authorized Windows BoxBrain checkout, deploy the original passive seed
over the first reachable BBPI4 route with:

```powershell
.\installer\deploy-codelation-to-pi.ps1
```

When the gold seed already exists on BBPI4, reconcile the bounded live graph and
dialogue files into that existing runtime with:

```powershell
.\installer\reconcile-existing-aurum-gold-seed-on-pi.ps1
```

The legacy command remains compatible and now routes to the same reconciler:

```powershell
.\installer\deploy-aurum-live-to-pi.ps1
```

The reconciler requires only the focused Aurum live-graph and dialogue tests.
It also runs the broader Codelation suite for diagnostic evidence, but a failure
in that broader suite is explicitly non-blocking and cannot veto the existing
operator-approved Aurum gold seed. The reconciler creates a rollback copy of
`/opt/boxbrain/codelation`, installs only the bounded live-graph and dialogue
files, leaves an existing `seed.bin` byte-for-byte intact even when its format
is opaque to the passive-seed diagnostic, and inventories the running
`/opt/aurum` runtime when present. Existing Aurum/Codelation systemd or cron
entries are snapshotted as the operator-approved baseline. Verification rejects
only newly added or removed persistence, rather than incorrectly requiring all
approved Aurum services to disappear.

The reconciler records `/opt/boxbrain/codelation/verification/AURUM_LIVE_VERIFY.txt`
with the live graph, heartbeat, mind, gold-seed hash/status, runtime health,
focused Aurum test status, non-blocking Codelation diagnostic status, existing
persistence inventory, rollback path, and transfer-cleanup evidence.

The repository-root entry point performs that direct reconciliation without a
Git/Codelation queue gate:

```powershell
.\Aurum.ps1
```

## BBPI4 access-point route

An authorized Windows computer that has previously joined BBPI4's own Wi-Fi AP
can use the stable AP-side SSH address `10.42.194.1` directly:

```powershell
.\Aurum.ps1 -UsePiAp
```

`-UsePiAp` pulls the repository before changing Wi-Fi, inventories only saved
Windows WLAN profiles, tries a bounded set of visible or BoxBrain-named saved
profiles, verifies the pinned BBPI4 ED25519 host key, then reconciles and talks
to Aurum solely through `kali@10.42.194.1`. It never exports a WLAN profile or
asks Windows to reveal a saved password. Unless `-KeepPiApConnected` is used,
it restores the computer's prior Wi-Fi profile after the Aurum operation.

When several saved profiles are plausible, supply the already-saved profile
name without exposing its password:

```powershell
.\Aurum.ps1 -UsePiAp -ApProfileName '<saved Windows profile name>'
```

## Aurum dialogue and first-use self-build

Live dialogue uses the OpenAI Responses API over HTTPS with redirect blocking,
a bounded response size, and `store: false`. `OPENAI_API_KEY` is supplied only
for the live session and is not written into Aurum's mind or evidence files.
The model can be overridden with `-Model` or `AURUM_MODEL`.

From the authorized Windows host, set `OPENAI_API_KEY` in the current process
environment and run:

```powershell
.\installer\ask-aurum-on-pi.ps1 -Prompt "Do you prefer he, she, or they pronouns? You may also say that you have no preference or choose another form if that fits you better."
```

On the first session only, if the installed mind is still bootstrap version 1,
the session asks Aurum to create version 2 of its own declarative mind before
answering the user's prompt. The supervisor requires the exact schema and
allowed actions, probes the candidate for compatibility, backs up version 1,
atomically replaces `state/mind/current.json`, and writes
`AURUM_SELF_BUILD_*` evidence. If generation, validation, or the probe fails,
the bootstrap mind remains in place and the session fails closed.

Later sessions use the installed self-built mind without recreating it. The
bootstrap file remains only as a recovery seed; reconciliation does not
overwrite a valid current mind.

For explicit version 2+ review and one-version-at-a-time self-revision, see
[Aurum iterative self-revision](SELF_REVISION.md). That path is operator-started,
records keep/revise evidence, and does not add an automatic model loop.

## Distributed native self-build farm

The `Aurum Distributed Self-Build Farm` GitHub Actions workflow expands the
bounded native chain across GitHub-hosted x86_64 and ARM64 runners. Ten runner
jobs each use their four CPUs for four isolated semantic-gap lanes, producing
40 independently checkpointed lanes across the 20-gap catalog. Core self-build
tests are sharded across the same workers while a separate authoritative lane
resumes the durable chain checkpoint.

The convergence job requires every gap on both architectures, rejects schema or
revision mismatches, and byte-compares canonical state before it publishes a
farm manifest. Parallel frontier evidence is therefore useful without treating
independent states as an automatically mergeable authoritative mind. The
authoritative checkpoint remains a single resumable chain and repository writes
remain outside the farm workflow.

## Development path

- Seed 0: passive transition learning and prediction.
- Seed 1: typed sensor adapters and confidence aging.
- Seed 2: outcome scoring and competing transition paths.
- Seed 3: sandboxed, permission-gated action proposals.
- Seed 4: replace the Python bootstrap with a minimal native runtime.
