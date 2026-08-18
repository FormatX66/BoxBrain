# Aurum machine substrate

Aurum must not confuse the current carrier with the capability it needs.

GitHub, Git, Python, Docker, QEMU, hosted runners, local PCs, and Raspberry Pis are bootstrap carriers. They are useful because they already exist, not because Aurum must permanently depend on their human-facing abstractions.

## Machine-native layers

### 1. Object ledger — Git-like capability without Git semantics

`machine_substrate.ObjectStore` is a minimal content-addressed substrate:

- immutable SHA-256 objects;
- canonical machine objects for trees, commits, execution results, and later arbitrary state;
- integrity verification on every read;
- mutable refs as the only names that move;
- parent-linked commits for durable history;
- carrier-independent byte representation.

Git can replicate this state today. The object graph itself does not require Git.

### 2. Capsules — runtime capability without Python semantics

A `Capsule` describes an execution requirement rather than a language-specific environment. It records:

- required capabilities;
- deterministic entrypoint intent;
- inputs and expected outputs;
- dependencies;
- environment contract;
- safe/adventurous/verification posture.

Current executors may be Python, shell, native programs, containers, or QEMU. A future Aurum VM, bytecode runtime, or direct machine-code executor can satisfy the same capsule without changing the scheduler or evidence model.

### 3. Processor farm — compute capability without machine ownership assumptions

`ProcessorFarm` schedules capsules against nodes by capability and available slots. It deliberately prefers the least-specialized node that can satisfy a job, preserving scarce/specialized capacity for work that actually needs it.

The first logical farm can span:

- GitHub-hosted x86-64 workers;
- GitHub-hosted ARM64 workers;
- bounded GPT/Python analysis;
- authorized self-hosted Windows nodes;
- BBPI4 and later physical Aurum nodes.

A node is a capability vector. The scheduler does not care whether the underlying compute is a cloud VM, container, physical CPU, FPGA, future accelerator, or Aurum-native processor service.

### 4. Evidence ledger — result capability without conversational memory

Every machine result can be reduced to immutable evidence plus a moving ref. Successful and failed results can coexist. Failed experiments are not deleted simply because they were not selected for promotion.

That permits branch/evolution behavior without relying on a chat transcript as the authoritative project state.

## Expansion rule

When Aurum encounters a missing tool, runtime, repository behavior, or compute capability:

1. describe the missing capability rather than the missing product name;
2. determine whether an existing carrier already satisfies it;
3. if not, implement the smallest machine-native capability layer;
4. add it as a node/runtime/object type rather than hard-coding the temporary carrier;
5. verify it independently;
6. retain the old carrier as a fallback until the new path converges.

The direction is therefore not "replace Git/Python/Docker for ideological reasons." The direction is "never allow the lack of one of them to become a fundamental architectural blocker."

## Current bootstrap

`machine_substrate.py` now supplies the first object ledger, capsule contract, capability scheduler, and execution evidence representation. The corresponding machine-fabric workflow fans work across independent hosted lanes and fans evidence back into one convergence artifact.
