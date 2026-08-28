# Aurum Seed Lifecycle

## Canonical law

**Boot once. Grow continuously.**

An Aurum seed is a small bootstrap organism, not a conventional installer image and not a recurring upgrade medium.

The seed exists to establish the minimum trusted machine state required for Aurum to begin growing on the hardware it inhabits. After a machine has a working Aurum seed, normal generations propagate from the running seed itself.

Canonical lifecycle:

1. boot the initial seed;
2. identify the machine and available capabilities;
3. establish trusted connectivity and local state;
4. discover the next authorized Aurum state;
5. pull or receive that state through an authorized path;
6. verify provenance, policy, compatibility, and integrity;
7. stage reversible changes;
8. apply the next state locally;
9. verify runtime and physical behavior;
10. retain rollback evidence;
11. continue growing from the new running state.

A normal Aurum generation must **not** require rebuilding, reflashing, or replacing boot media.

## Boot media

Boot media is bootstrap/recovery infrastructure only. It is appropriate for:

- the first seed on otherwise blank hardware;
- catastrophic storage failure when no working Aurum state remains;
- deliberate bare-metal recovery or re-seeding explicitly chosen by the operator.

Boot media is **not** part of the normal update path for Hopper or any established Aurum node.

GUI changes, GPT integration, AinWeave growth, StateWeave, ComputeWeave, drivers, local LLM updates, autonomy changes, and future generations must grow through the running seed unless a true recovery condition exists.

When a true recovery condition exists, recovery media must be one-shot,
machine-bound, and narrower than an installer. It must identify the installed
machine and current seed before writing, preserve the displaced state as
evidence, change only an explicit allowlist, prove the recovered state, and
leave the next boot on the normal running-seed path. A recovery image must not
silently become recurring update media.

## Design consequence

Aurum should always prefer propagation over installation:

**current seed -> discover -> pull -> verify -> stage -> apply -> prove -> become next seed**

The long-term goal is that even first contact with new hardware can increasingly be seeded by another authorized Aurum node or trusted local transport, reducing dependence on manually prepared media further.

This rule is architectural, not a Hopper-specific convenience.

## Runtime state is not seed source

The running seed's tracked workspace is immutable during ordinary interaction.
Temporary presentation choices, including GPT-requested color and theme previews,
live in bounded runtime state outside Git. They can be reset immediately, reset
automatically on reboot, and never make the seed workspace dirty.

Permanent presentation changes are promoted only as a verified next seed. A
runtime experiment must therefore never block discover, pull, verify, stage, or
apply. Resident GPT retains bounded control and receipts, but it cannot directly
replace tracked seed source or push Git.

## Generation proof

Every running-seed generation records its authorized repository, branch, commit
and tree; source verification; staged file manifest; rollback location; applied
hash proof; physical projection result; bounded GPT executor receipt; and the
final `become_next_seed` decision. Hopper publishes a sanitized view of this
receipt through its read-only self-debug status channel.

`become_next_seed` is true only after installed runtime hashes, bounded GPT
execution, system activation, a real physical projection, keyboard and pointer
events in the current GUI boot, the bounded GUI recovery console, and Wi-Fi
profile/connectivity persistence across the update have all passed. The
physical receipt distinguishes the primary HTML renderer from the automatic
Pygame fallback instead of treating either path as implied success. Input
receipts record only event counts and timestamps; Wi-Fi receipts contain only
opaque path identities, hashes, sizes, modes, and connectivity state, never
SSID or credential contents.

An applied generation that has not yet observed both physical input paths stays
`applied-not-proven`. A later normal growth cycle can complete proof after the
operator uses the keyboard and pointer, but it cannot silently become the next
seed. The same rule applies if a saved Wi-Fi profile or previously online state
does not survive the update.

An unavailable OpenAI credential may leave the model-call portion unproven, but
it does not remove or weaken the local bounded executor. Experimental Aurum LLM
adapter training remains outside this generation gate.

## Machine-sealed GPT credential

Hopper creates a root-owned credential receiver and publishes only its public
key and fingerprint through the read-only self-debug proof. The authorized
operator seals the existing OpenAI key to that exact receiver. Git carries only
the ciphertext envelope; Hopper decrypts it into a root-only file under `/run`.

The HTML projection never asks for, receives, stores, or returns the key. A
reboot recreates the runtime credential from the same target-bound envelope,
and proof reports only readiness, hashes, and the model-call result. The key
value is never source, UI, receipt, or log data.
