# TR8:PROMPT — Aurum/GPT Prompt Surface

`TR8:PROMPT` restores the prompt area to the Aurum Gen1 human surface while keeping model/provider details behind a stable capability boundary.

## User surface

The graphical prompt area exposes two explicit modes:

- **Aurum** — sends intent to the local Aurum intent adapter when one is present.
- **GPT** — sends a prompt through the configured OpenAI API adapter when credentials are available.

The same surface always includes **Open Web** so the user can move directly into `TR8:WEB`. If GPT API credentials are not configured, the shell must remain usable and offer **Open ChatGPT** through `aurum-web` rather than failing.

## Security and authority

- The local prompt service listens on loopback only.
- No API key is embedded in the image, repository, HTML, logs, or browser profile.
- `OPENAI_API_KEY` may be supplied at runtime by the service environment or by a root-readable Aurum credential file outside the user web surface.
- Web content never receives Aurum/Farmer execution authority merely because it is opened from the prompt area.
- Farmer objectives remain a separate bounded execution path with independent verification.

## Stable interfaces

- `/usr/local/bin/aurum-prompt` — open the local prompt surface.
- `/usr/local/lib/aurum/prompt/server.py` — loopback prompt service.
- `http://127.0.0.1:8765/` — local graphical surface.
- `/api/aurum` — local Aurum intent adapter.
- `/api/gpt` — GPT adapter.
- `/healthz` — readiness probe.

## Seed acceptance

A seed candidate passes this capability gate when:

1. the local service starts without root web exposure;
2. `/healthz` responds;
3. the prompt page renders;
4. Aurum mode fails gracefully when no local intent adapter is installed;
5. GPT mode fails gracefully when no API credential is configured;
6. `Open Web` invokes the stable `aurum-web` interface;
7. no secret appears in generated files or process arguments.
