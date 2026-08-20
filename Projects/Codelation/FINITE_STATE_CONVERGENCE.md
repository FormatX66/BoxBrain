# Aurum finite-state convergence

Aurum should not wait for a deterministic computer failure to become a human troubleshooting conversation. In the testing world, the machine variables are finite, their constraints are knowable, and many distinct paths stop mattering after they reach the same downstream invariant.

## Core rule

For every bounded subsystem:

1. Declare the variables that can change the result and the finite values currently known for each variable.
2. Remove impossible combinations with explicit constraints rather than testing meaningless permutations.
3. Execute or simulate every remaining meaningful state.
4. Collapse states at convergence points as soon as their earlier differences no longer affect downstream behavior.
5. Require every modeled failure class to have detection evidence, autonomous recovery actions, and a convergence target.
6. Preserve failed candidates as evidence; do not erase successful branches or replace the known-good generation just because another branch failed.
7. Treat a real-machine result that was not predicted by the model as new evidence. Add the smallest new variable/domain value that explains it, fork a hypothesis, and replay the bounded sweep.

The desired loop is:

`enumerate -> constrain -> test -> observe -> converge -> compose -> verify`

not:

`boot -> fail -> ask a human for a command -> try another command`.

## Convergence prevents combinatorial explosion

Independent internal permutations should not be cross-multiplied after a subsystem has reached its contract. For example, several boot media layouts and loader paths may all converge to `payload-verified`. Kernel testing should consume the `payload-verified` contract rather than multiplying every kernel case by every historical boot permutation.

The same pattern applies to:

- firmware and loader -> payload verified
- payload and storage discovery -> kernel running
- kernel and root discovery -> local Aurum runtime
- display/input variants -> local/headless Aurum capability
- network variants -> online or explicitly classified offline operation
- runtime candidate branches -> known-good generation remains runnable
- self-build branches -> verified generation or preserved failed hypothesis

This makes the useful test count closer to the sum of bounded subsystem spaces than the product of every low-level variable in the machine.

## Promotion contract

A testing-world change is promotable only when:

- all declared variable domains were considered;
- constraint pruning is deterministic and auditable;
- no modeled failure terminates in a human shell/procedure;
- required subsystem invariants converge to the expected class count;
- failed branches remain inspectable;
- physical-only claims are not promoted without physical evidence.

## Current implementation

`Projects/Codelation/state_space.py` provides the reusable finite-state solver.

`Projects/AurumPC/aurum_boot_state.py` is the first concrete model. It encodes the PC boot variables, explicit impossible combinations, convergence stages, the PC-01 GRUB-shell observation, and the recovery catalogue that replaces manual GRUB troubleshooting in the test world.

The existing Aurum PC workflow already discovers every test under `Projects/AurumPC/tests`, so the state-space contract is continuously exercised on Aurum agent branches and on the verified trunk after promotion.
