# Aurum Tiny Seed Failure Playbook

Purpose: be one or two steps ahead of the operator during physical Tiny Seed and recovery proof. A report as short as **"it didn't work"** should map immediately to a bounded evidence path rather than restart diagnosis from zero.

## Priority order

This order is probability × impact on the current completion path, not a claim that every item will fail.

### 1. Physical x86 boot/display failure

Likely report: blank screen, frozen logo/menu, no Tiny Seed surface, or boot text stops before `AURUM_TINYSEED_READY`.

Prepared response:
- Do not touch the installed Aurum/LKG.
- Retry the same media using **Aurum Tiny Seed (safe verbose)**. This adds `nomodeset`, visible systemd status, and high kernel log verbosity while keeping the same read-only/live recovery intent.
- If the normal path reaches userspace but the setup service fails, `OnFailure=aurum-triage.service` captures `/var/lib/aurum/evidence/triage-latest.json` automatically.
- If neither normal nor safe verbose reaches userspace, capture the first visible boot error/photo. The failure is below the userspace triage boundary; rebuild only after identifying firmware/bootloader/kernel evidence.

### 2. Media write or readback failure

Likely report: flash tool errors, media is not bootable, hash/readback differs, or more than one candidate disk is present.

Prepared response:
- Never guess the target disk.
- Require artifact checksum before write and a readback/integrity proof after write.
- If target identity is ambiguous, stop without writing and reduce the machine to exactly one explicitly intended non-system removable target.
- Preserve the known recovery medium; Tiny Seed testing uses separate media.

### 3. Network unavailable after Tiny Seed boots

Likely report: no Wi-Fi, no network list, password succeeds but no route, Git fetch fails.

Prepared response:
- The protected germ/LKG remains unchanged.
- `aurum-triage` checks NetworkManager plus the default route and returns `NETWORK_NOT_READY` before regrowth is attempted.
- Prefer Ethernet if present, otherwise use the Tiny Seed retry/rescan screen to join Wi-Fi. Network failure never silently selects offline mode; continuing offline requires an explicit choice.
- If an install/repair is offline and the verified x86 fallback carrier is present, Tiny Seed grows that pinned phenotype into the inactive slot without granting network authority. It must still report its exact genetics/platform commits and pass every Guardian gate.
- If no valid carrier is present, Tiny Seed keeps the live console actionable and offers **Join Wi-Fi now** before deferral. A successful join resumes regrowth against the already prepared root without repeating target selection or destructive work.
- A fallback phenotype must be called `offline-carrier`, never `current`, unless its recorded immutable commits equal the current trusted genetics and platform heads.

### 4. Existing Aurum/install target ambiguity

Likely report: Tiny Seed sees the wrong disk, multiple Aurum installations, multiple possible targets, or no safe target.

Prepared response:
- No destructive fallback is permitted.
- One existing Aurum root means repair/reseed automatically; multiple existing roots require explicit selection; no unambiguous safe target means stop without writing.
- Inspect `lsblk`/Tiny Seed target evidence through `aurum-triage` before changing installer logic.

### 5. Genetics regrow/fetch/build failure

Likely report: fetch failed, manifest refused, platform source missing, candidate build failed, or regrow stopped before `trial-armed`.

Prepared response:
- Keep active/LKG untouched.
- Use `/var/lib/aurum/germ/latest-regrow.json` and triage code `REGROW_INCOMPLETE` as the first evidence.
- Repair only the failed fetch/manifest/platform/build dependency, then rebuild the inactive slot from an immutable resolved commit.
- Never convert a failed candidate into the active slot manually.

### 6. Candidate boots but Guardian rejects it

Likely report: system reboots back to the old state, new candidate disappears, or user says the update "didn't stick."

Prepared response:
- Treat automatic rollback as a successful recovery protection event, not a failed safety system.
- `guardian.py` preserves LKG, quarantines the failed candidate, and records a `rolled-back:<reason>` result.
- `aurum-triage` maps that state to `CANDIDATE_ROLLED_BACK`.
- Diagnose the health evidence/quarantine record, repair the candidate, and run a new inactive-slot trial. Do not weaken the health gate.

### 7. Pi-specific boot/peripheral mismatch

Likely report: Pi has power but no useful console, UART differs, image boots but network/input differs, or platform adapter is insufficient.

Prepared response:
- Pi media carries UART output and a `cmdline.aurum-safe.txt` verbose fallback on the boot partition.
- If Ethernet link is present but SSH is absent, inspect the configured USB HDMI capture before changing network state. A visible vendor username prompt indicates the wrong/old image or a missing wizard mask, not a network fault.
- For an early-KVM-prepared image, verify the bootstrap receipt and pinned controller status. No boot authority means no listener by design; malformed authority must remain unconsumed and inactive.
- A KVM disconnect releases every pressed key/button. Use `release-all` before retrying input; do not rebind a physical input driver.
- Use the safe cmdline only for diagnosis; it does not change LKG/root state.
- ARM64 promotion remains constrained by the platform adapter/evidence contract. A static CI image is not physical Pi proof.

### 8. Signed remote recovery does not act

Likely report: recovery command is ignored or returns disabled/refused.

Prepared response:
- Fail-closed is expected unless an authority public key is enrolled and the request is fresh, machine-addressed, signed, non-replayed, and trusted.
- Specific recovery additionally pins both genetics and platform-source commits.
- Do not bypass signature/freshness/trust checks to make remote recovery appear functional.

## Fast operator mapping

If the only report is **"it didn't work"**, first determine the highest stage that was visibly reached:

1. No firmware/boot menu -> firmware/media path.
2. Boot menu but no Linux/userspace -> safe verbose boot path.
3. Linux/userspace visible -> run/read `aurum-triage`.
4. Tiny Seed UI visible but networking fails -> network branch.
5. Target-selection screen is wrong/ambiguous -> target branch.
6. Regrow starts but does not arm trial -> regrow branch.
7. Trial reboots back to LKG -> candidate-health/quarantine branch.

Always preserve the last proven state while collecting evidence.
