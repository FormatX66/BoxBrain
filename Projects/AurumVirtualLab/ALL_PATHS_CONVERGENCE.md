# Aurum all-paths convergence sweep

This marker defines the integration lane that preserves the previously green self-build and virtual-hardware commit while adding the verified GUI and local LLM subtrees.

The convergence sweep must exercise these independent paths on the same source lineage:

- Aurum GUI source validation and local HTTP smoke test
- Aurum local LLM build and inference smoke test
- Aurum PC image build and UEFI boot smoke test
- Aurum Pi3 image build and structure verification
- Codelation parallel capability buildout
- Distributed 40-lane x86_64/aarch64 self-build convergence
- Four-target virtual hardware convergence: Docker x86_64, Docker ARM64, QEMU x86_64 UEFI, and QEMU Pi3 machine/runtime

A failure in one path does not erase successful evidence from another path. Integration promotion requires the exact convergence commit to be green across the required gates.
