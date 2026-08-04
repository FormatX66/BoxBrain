# Agent Handoff

## Current objective

Deploy and click-verify the Kali headless Windows shortcut.

## Tasks

1. Run full validation and commit the shortcut source.
2. Install the fixed helper root-owned and the desktop entry owned by `kali`.
3. Verify POSIX parsing, file modes, and target selection.
4. Launch once from the Kali desktop and confirm the restricted prompt.

## Dependencies

- Exactly one connected, verified USB target in the BoxBrain registry.
- Existing Pi target identity and pinned known-hosts file.
- XFCE desktop terminal support.

## Files affected

- `edge/kali-pi-agent/scripts/open-headless-windows.sh`
- `edge/kali-pi-agent/scripts/install-desktop-shortcut.sh`
- `edge/kali-pi-agent/desktop/boxbrain-headless-windows.desktop`
- Tests, documentation, and session indexes.

## Required repositories

- `FormatX66/BoxBrain`

## Verification checklist

- Refuse zero or multiple connected USB targets.
- Restrict addresses to the dedicated USB subnet.
- Retain `StrictHostKeyChecking=yes` and the Pi trust store.
- Never run enrollment or accept a new key.
- Install only the fixed helper and one desktop entry.

## Suggested commit message

`Add Kali headless Windows desktop shortcut`

## Suggested branch

`codex/kali-headless-shortcut`

## Potential risks

- A disconnected or ambiguous registry must fail closed.
- The target account intentionally remains non-administrator.

## Estimated completion order

Validation, commit, installation, file verification, click proof.
