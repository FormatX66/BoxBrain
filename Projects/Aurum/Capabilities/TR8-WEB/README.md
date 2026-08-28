# TR8:WEB — Aurum Web Capability

`TR8:WEB` is Aurum Gen1's durable web-access trait. The user-facing capability is stable even when the compatibility engine underneath changes.

## Gen1 materialization

The first implementation uses an available Linux browser engine in this preference order:

1. Chromium (`chromium`)
2. Chromium Browser (`chromium-browser`)
3. Firefox ESR (`firefox-esr`)
4. Firefox (`firefox`)

The materializer installs Chromium when possible, creates an Aurum-owned browser profile, and exposes a single stable launcher at `/usr/local/bin/aurum-web`.

## Required behavior

- launch from the graphical Aurum shell without a terminal
- open a URL supplied by Aurum intent or the user
- default to a normal new-tab/browser surface when no URL is supplied
- preserve bookmarks, history, cookies and user preferences in an Aurum user profile
- permit downloads into the user's normal Downloads projection
- use the working system network/DNS stack; TR8:WEB must not own Wi-Fi configuration
- recover from a crashed browser process without destabilizing the shell
- never run the browser as root
- retain a conventional-browser fallback while native Aurum web components evolve

## Security boundary

The browser is an untrusted-content boundary. Web content does not receive Aurum system authority merely because it is displayed by TR8:WEB. The compatibility browser retains its normal sandbox unless an explicitly documented compatibility exception is required and separately verified.

## Acceptance gate

Run `acceptance.sh` after materialization. Physical Gen1 acceptance additionally requires keyboard/pointer operation and visible rendering on the target machine.
