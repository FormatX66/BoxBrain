# Aurum Genetics and Reseed Germ Architecture

Status: **Mandatory seed contract**

## Core model

Aurum is not distributed as a sequence of frozen operating-system images.

- **GitHub is the genetics**: the authoritative current rules, capabilities, manifests, build instructions, tests, recovery policy, and reproducible inputs that describe what Aurum should grow into.
- **A local seed is a viable organism**: enough Aurum exists locally to observe the machine, reach the genetics, stage a candidate, validate it, and recover.
- **The running machine is the phenotype**: the current hardware-specific expression of those genetics plus preserved local identity, learned state, evidence, and authorized user state.
- **Reseeding is regrowth**: fetch trusted genetics, grow a new candidate beside the existing organism, adapt it to the actual machine, validate it, then promote it only if healthy.

The normal recovery question is therefore not "which release image should be restored?" It is "can the germ reach trusted genetics and regrow a healthy candidate?"

## Universal reseed invariant

> Any viable Aurum seed must be able to regrow into the current trusted Aurum genetics without first becoming every intermediate historical generation.

A seed may be old. It may have missed many generations. Its user interface may be damaged. Its adaptive layer may be partially broken. If its protected germ can still execute, identify the machine, access a transport, and authenticate the trusted genetics source, it must be able to stage current genetics directly.

Historical generations remain valuable for provenance, diagnosis, reproducibility, and deliberate rollback. They are not mandatory stepping stones during normal reseeding.

## The protected Reseed Germ

Every post-germ Aurum seed must contain a small, conservative, independently testable **Reseed Germ**. The germ is not the full Aurum runtime. Its responsibilities are intentionally narrow:

1. identify enough hardware and storage topology to avoid destructive ambiguity;
2. establish or use an authorized transport to the trusted genetics source;
3. resolve a trusted genetics ref or specifically requested trusted commit;
4. stage genetics into a new candidate area without modifying the active organism;
5. validate the genetics manifest and germ protocol compatibility;
6. invoke the hardware-specific growth/build contract in the candidate;
7. require candidate health evidence before activation;
8. preserve the current viable organism until promotion succeeds;
9. write receipts/provenance for fetch, growth, validation, promotion, or refusal;
10. fall back to local recovery media when network genetics are unavailable.

The germ must remain substantially smaller and less mutable than the adaptive Aurum runtime.

## Stable germ protocol

The germ protocol is versioned independently from Aurum generations.

A current genetics manifest declares the minimum germ protocol it supports. An old germ must either:

- understand the current manifest and proceed safely; or
- refuse mutation and report that a newer germ/recovery medium is required.

It must never guess its way through an unknown manifest schema.

The stable repository path for protocol v1 is:

`Projects/Aurum/Germ/GENETICS.json`

The stable bootstrap implementation path is:

`Projects/Aurum/Germ/reseed.py`

These paths are compatibility surfaces. They must not be silently repurposed.

## Genetics manifest contract

The current genetics manifest identifies at minimum:

- schema and germ protocol;
- authoritative repository identity;
- default trusted ref for current genetics;
- required genetics paths;
- candidate-only staging rule;
- live-overwrite prohibition;
- health-evidence requirement for promotion;
- provenance/receipt requirements.

A branch such as `main` can represent the current genetics, while a full commit SHA can pin a deliberate historical or diagnostic target.

## Regrowth flow

`any viable seed -> protected germ -> resolve trusted genetics -> stage candidate -> hardware-specific growth -> test/health gate -> promote -> current Aurum`

The active organism is not overwritten during fetch or build.

If growth fails:

`candidate failure -> preserve active organism -> record receipt -> quarantine/discard candidate -> retry current genetics or select a trusted historical target`

## Relationship to A/B and Last Known Good

A/B slots and Last Known Good remain useful survival mechanisms, but their role is local continuity rather than release management.

- **A/B** gives the germ somewhere safe to grow a candidate beside the active organism.
- **LKG** is the last locally proven phenotype that can keep the machine alive while a candidate is grown or when genetics are unreachable.
- **Git genetics** are the durable recipe for regrowth.

LKG is not the definition of Aurum and does not need to be the newest genetics. It is a local survival anchor.

## External recovery medium

A recovery USB is an external germ carrier, not a conventional installer archive that must stay synchronized generation-by-generation.

Its long-term job is to provide a known-good protected germ capable of:

- diagnosing the local organism;
- reaching current genetics;
- staging/reseeding current genetics;
- selecting a specific trusted commit when requested;
- repairing local boot/recovery metadata;
- preserving or restoring local identity/state when safe.

The recovery medium may contain a fallback phenotype for offline emergencies, but that fallback is secondary to the germ/regrowth role. A fallback must be pinned by the genetics policy, cover every carried regular file with deterministic tree hashes, record both the genetics and platform commits, and be permitted to grow only an inactive non-LKG slot. It never bypasses preboot validation, Guardian trial boot, postboot health promotion, journaling, quarantine, or rollback.

## Pre-germ compatibility

Seeds created before the protected germ existed cannot retroactively gain it. They are supported through either:

1. an external recovery medium carrying the germ; or
2. a deliberately tested compatibility bridge exposed through a repository branch the old seed can already reach.

Once a pre-germ machine is recovered, installing the protected germ is the first required mutation before normal adaptive growth resumes.

## Security and trust

GitHub is genetics storage and a recovery control plane, not an unrestricted shell.

The germ must:

- allowlist repository identity;
- resolve and record an immutable commit SHA before growth;
- preserve fetched commit and manifest provenance;
- reject incompatible manifest schemas/protocols;
- never overwrite the active organism during staging;
- require explicit authorization for network access where policy requires it;
- require health evidence before promotion;
- support stronger signed-manifest / protected-ref verification as the trust layer matures.

## Architectural consequence

Commands named `git-sync`, `update`, or similar must not be treated as the core Aurum evolution mechanism. A source-tree fast-forward is only transport. The actual lifecycle is **resolve genetics -> grow candidate -> verify phenotype -> promote**.

## Design principle

**Git stores the genetics. Seeds carry the germ. Machines regrow the phenotype.**
