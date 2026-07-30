# Execution Plan

## 1. Completed Raspberry Pi controller deployment

1. [x] Inventory Pi Python, systemd, network interfaces, services, paths, and
   ports without changing them.
2. [x] Add immutable wheel deployment with exact runtime dependencies.
3. [x] Create a dedicated non-login service account and private state layout.
4. [x] Verify helper checksum and deployment provenance.
5. [x] Pass authenticated foreground health before activation.
6. [x] Enable the USB-bound hardened systemd service.
7. [x] Verify unauthorized rejection, private modes, helper integrity,
   emergency-stop persistence, and restart recovery.
8. [x] Run controller and Flutter regressions.
9. [x] Commit, push, and open stacked draft pull request 6.

## 2. Prepare the isolated Windows RDP target

1. Select an operator-owned disposable Windows VM or physical sandbox.
2. Isolate its network and remove sensitive files and accounts.
3. Snapshot the clean state.
4. Enable RDP only for the bounded live-lab window.
5. Record endpoint identity and certificate fingerprint independently.
6. Define the controlled dashboard session credential flow.

## 3. Run certificate-only live verification

1. Register the target disabled.
2. Probe an exact certificate match without credentials.
3. Confirm the verification timestamp and bounded audit record.
4. Rotate or substitute the fixture certificate and confirm atomic disablement.
5. Test unreachable and bounded-timeout behavior.
6. Confirm no authentication, desktop session, frame, or input occurs.
7. Restore the target snapshot and retain only approved redacted evidence.

## Completion gates

- Pi service and helper identities continue to match provenance.
- Controller API remains USB-only and authentication remains fail-closed.
- Controller credentials and runtime data stay outside Git.
- Only an explicitly authorized disposable target is contacted.
- No RDP credential, desktop session, frame, input, shell, clipboard, file, or
  device redirection enters the certificate-only milestone.
- All BrainConnect and BoxBrain validation passes.
