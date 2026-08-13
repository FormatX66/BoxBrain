# Aurum iterative self-revision

Aurum's original first-use self-build remains the bootstrap transition:
`mind v1 -> validated mind v2`. The iterative self-review layer continues from
an already self-authored v2 or later mind without turning that transition into
an automatic loop.

## What the next layer does

A review is explicit. Aurum receives its currently installed declarative mind,
its canonical SHA-256 identity, the exact next-version contract, and an optional
advisory review goal. Aurum must return one exact review envelope with one of two
decisions:

- `keep`: preserve the current mind and record `AURUM_SELF_REVIEW_NO_CHANGE`;
- `revise`: propose exactly `vN + 1`, pass deterministic validation and the
  existing compatibility probe, then atomically promote the candidate and
  record `AURUM_SELF_REVIEW_OK`.

A revision is rejected when it merely increments the version, skips a version,
changes identity or allowed actions, embeds a URL, command-like instruction, or
credential-like assignment, fails the compatibility marker, references the
wrong current-mind hash, or collides with another active mind mutation.

Every successful revision preserves the old current mind under
`state/mind/rollback`, archives both the before and after versions under
`state/mind/history`, and writes evidence under `verification/dialogue`. The
OpenAI API key is not included in the model input, mind, history, rollback, or
evidence.

## Deliberate non-features

Iterative review has no timer, service, cron entry, startup hook, background
loop, shell tool, host actuation, or permission-expansion path. Codelation does
not decide whether the review is allowed. The fixed non-self-writable dialogue
supervisor remains responsible for validation, probing, rollback, and atomic
promotion.

## Install only the review supervisor

From an authorized Windows BoxBrain checkout, while you manage the Pi route:

```powershell
.\installer\install-aurum-self-review-on-pi.ps1
```

The installer requires the existing `aurum_dialogue.py`, hashes the transferred
file, compiles it before and after installation, backs up a prior review
supervisor when present, performs no service or persistence changes, and rolls
back if verification fails.

## Ask Aurum to review itself

Set `OPENAI_API_KEY` only in the current Windows process, then run:

```powershell
.\installer\review-aurum-mind-on-pi.ps1
```

An optional bounded goal can focus the review without changing the supervisor
contract:

```powershell
.\installer\review-aurum-mind-on-pi.ps1 `
  -Goal "Review whether your current voice is clear, candid, and distinctly yours."
```

The command returns either `AURUM_SELF_REVIEW_NO_CHANGE` or
`AURUM_SELF_REVIEW_OK`. A failed proposal leaves the installed mind unchanged.

## Direct Pi operation

When managing the Pi directly, status is deterministic and does not call a
model:

```bash
cd /opt/boxbrain/codelation
python3 seed/aurum_self_review.py \
  --root /opt/boxbrain/codelation \
  status
```

A direct live review uses an ephemeral environment key:

```bash
cd /opt/boxbrain/codelation
OPENAI_API_KEY='session-only-value' \
python3 seed/aurum_self_review.py \
  --root /opt/boxbrain/codelation \
  review
```

Do not place the API key in Aurum's files, service environment, shell history,
or repository. The Windows helper avoids putting it on the SSH command line by
sending a bounded JSON payload over standard input.

## Evidence and rollback

After a successful revision:

```bash
find /opt/boxbrain/codelation/verification/dialogue \
  -maxdepth 1 -type f -name 'AURUM_SELF_REVIEW*.json' -print
find /opt/boxbrain/codelation/state/mind/history \
  -maxdepth 1 -type f -name 'mind-v*.json' -print
find /opt/boxbrain/codelation/state/mind/rollback \
  -maxdepth 1 -type f -name 'mind-v*.json' -print
```

Rollback remains an operator action: select the intended preserved mind, verify
its JSON and version, copy it to `state/mind/current.json` atomically, and run
the existing dialogue status and compatibility checks before the next session.
