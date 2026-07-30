# Execution Plan

## Milestone 1 - Consolidated Pi promotion

1. Extend the existing native installer rather than creating a duplicate.
2. Select `probe` or `control` explicitly.
3. Bind source revision, image ID, architecture, runtime package, ELF checksum,
   install path, and rollback path.
4. Run control identity and credential-negative fixtures before install.
5. Leave the production controller executor disabled.

## Milestone 2 - Runtime credentials and session self-test

1. Confirm a dedicated non-administrator Windows RDP account.
2. Verify systemd encrypted-credential support on the Pi.
3. Create target-UUID-bound username, password, and optional domain
   credentials without copying values to project files or command arguments.
4. Add a service drop-in and verify only the credential directory path is
   inherited.
5. Authenticate, verify the pinned desktop session, and disconnect with no
   input.

## Milestone 3 - First live pointer evidence

1. Confirm the VM checkpoint and certificate immediately before the run.
2. Capture bounded independent cursor evidence.
3. Queue one absolute pointer move.
4. Enable execution only for the reviewed connector and run one operation.
5. Record accepted-event result separately from visual-change evidence.
6. Disable execution immediately after the result.

## Milestone 4 - Rollback and expansion decision

1. Remove or deactivate the runtime credential drop-in.
2. Restore and verify `clean-linked-2026-07-29`.
3. Re-probe the RDP certificate and resolve any identity rotation.
4. Update BrainConnect, BoxBrain, and the next handoff.
5. Expand only the capability or evidence gap justified by the observed run.
