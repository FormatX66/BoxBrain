# TR8:PROMPT — Aurum / GPT Prompt Capability

`TR8:PROMPT` restores the resident Aurum/GPT prompt area as a first-class Gen1 shell capability while keeping authority bounded.

## Surface

- presents one local graphical prompt surface from the Aurum shell
- lets the user select **Aurum** or **GPT** behavior without exposing a terminal
- keeps the web address/search field connected to `TR8:WEB`
- serves the prompt UI only on loopback
- never embeds API credentials in Git, the seed image, HTML, receipts, or logs

## Aurum mode

Aurum mode is local-first. It forwards intent only to an explicitly configured bounded Aurum intent endpoint. If no local intent endpoint is configured, the UI reports that local Aurum intent is unavailable instead of inventing host authority.

## GPT mode

When `OPENAI_API_KEY` is present in the runtime environment, the loopback service can call the configured OpenAI Responses API model. When no credential is available, GPT mode degrades safely to an **Open ChatGPT** action through `TR8:WEB`; the shell remains usable and no secret prompt is shown.

## Security boundary

- listener defaults to `127.0.0.1` only
- no raw shell endpoint
- no repository-write endpoint
- no Farmer authority is granted to web content
- prompt history is browser-local unless a later Aurum storage trait explicitly owns it
- external URLs launch through the stable `aurum-web` capability

## Acceptance

A seed candidate is not promotable merely because these files exist. Acceptance requires the graphical surface to launch, the loopback service to remain local-only, web search/address routing to work, GPT-without-key fallback to remain stable, and the existing Wi-Fi, landscape graphics, and Last Known Good state to remain intact.
