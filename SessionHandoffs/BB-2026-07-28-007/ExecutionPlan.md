# Execution Plan

## 1. Completed Raspberry Pi helper deployment

1. [x] Locate and identify the Pi over the direct USB gadget network.
2. [x] Verify architecture, OS, disk, SSH identity, runtime, and sudo access.
3. [x] Add strict target, version, existing-file, and checksum gates.
4. [x] Extract the reviewed arm64 ELF from the Docker image.
5. [x] Run the full native boundary test on the Pi before install.
6. [x] Install root-owned binary and content-addressed provenance.
7. [x] Verify permissions, checksum, idempotency, and temporary cleanup.
8. [x] Reverify native, controller, and Flutter applications.
9. [x] Commit, push, and open stacked draft pull request 5.

## 2. Deploy the controller on the Pi

1. Inspect the host without changing services.
2. Select a dedicated application, runtime-data, and service-account layout.
3. Package the exact controller revision and pinned dependencies.
4. Run tests and a foreground localhost-only controller.
5. Configure API authentication, database, audit storage, emergency stop, and
   installed helper path outside Git.
6. Verify health and restart behavior without probing a real target.
7. Add a hardened systemd unit only after explicit authorization.

## 3. Verify an isolated Windows target

1. Select and snapshot the disposable Windows VM.
2. Obtain its RDP certificate fingerprint independently.
3. Register it disabled in BrainConnect.
4. Run exact-match, mismatch, timeout, and unreachable probes.
5. Confirm bounded audit events and no authentication or desktop session.
6. Revert the target snapshot and retain only redacted evidence.

## Completion gates

- Pi runtime identity continues to match provenance.
- Controller secrets and runtime data stay outside Git.
- No service is created or enabled without explicit authorization.
- No credentials, desktop session, frames, or input capability enter the
  certificate-probe milestones.
- All native, controller, Flutter, and BoxBrain validation passes.
