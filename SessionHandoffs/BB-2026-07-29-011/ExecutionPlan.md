# Execution Plan

## Daytime lane - low impact

1. Ask the operator to confirm scrolling, shell, or clipboard.
2. Keep the current FreeRDP compatibility boundary unless the operator
   requests a baseline change.
3. Prepare strict payload limits and tests for the selected capability.
4. Use focused local tests and documentation checks only.
5. Leave the Pi, VM, Docker, Flutter toolchain, and checkpoint chain untouched.

## Nightshift lane - ordered heavy work

1. Confirm the Pi is inert and the Windows VM uses
   `clean-linked-rotated-2026-07-29`.
2. Exercise enabled-drop-in refusal without uploading or installing a new
   revision.
3. Disable and verify execution, then exercise the successful upgrade path.
4. Run the full controller and Flutter suites.
5. Build and test native artifacts for amd64 and arm64.
6. Run the exact FreeRDP 3.26 identity/control gates on the Pi.
7. Restore the rotated checkpoint and perform one bounded selected-capability
   proof with independent evidence.
8. Disable execution, remove all credentials, drop-ins, and temporary runners,
   restore the checkpoint, and verify final certificate identity.
9. Update both repositories, validate links, commit, push, and generate the
   next handoff.

## Stop conditions

- Stop before mutation if configuration and authenticated live health disagree.
- Stop if the target certificate no longer matches.
- Stop if the VM is not at the rotated checkpoint.
- Stop if any secret appears in output or a repository.
- Never restore or delete `clean-linked-2026-07-29`.
