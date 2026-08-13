# Aurum-Morris capability growth

Pinned node: `825e5a7b7d4a7aed` (`Aurum-Morris`).

Aurum-Morris currently has two deployed-worker capability names in the existing worker design:

- `bbpi4-bootstrap`
- `connectivity-observation`

The prototype-builder growth path is evidence-gated rather than a general Windows execution grant:

1. `resource-observation`
   - read-only local machine capacity evidence
   - CPU, memory, storage, sparse-file support, GPU identity summary, and isolation-carrier availability
   - no partition changes, raw disk writes, or arbitrary process execution
2. `slush-extent-plan`
   - deterministic plan only
   - preferred 64 GiB, minimum 32 GiB, retain at least 32 GiB host reserve
3. `slush-extent-provision`
   - only after a verified plan and local write approval
   - fixed Aurum Slush path
   - sparse carrier only
   - no partition shrink, raw disk write, overwrite, or boot change
4. `slush-seed`
   - only after the extent is verified
   - content-addressed Aurum seed and mirrored recovery anchors
5. `prototype-runtime-materialize`
   - only after an isolated runtime carrier is verified (for example an available Hyper-V/VHD carrier)
   - host Windows boot remains unchanged
   - rollback evidence is mandatory before promotion

The machine-independent implementation is `windows_node_growth.py`; `morris_slush_extent.py` defines the storage contract.

Current verification status:

- eight independent capacity-mesh lanes: pass on workflow run `31733536827`
- integrated suite: 52 of 53 tests passed; one test-harness assertion incorrectly treated `Field.project()` binary output as a mapping
- attempted test-harness correction was blocked by the platform write classifier
- attempted Windows resource-observation carrier write was blocked by the platform write classifier
- no new capability has been deployed on Morris and no host storage has been changed

A capability is not advertised as live merely because this contract exists. Live promotion requires a real Morris observation/result artifact and the worker carrier to be deployed and verified.
