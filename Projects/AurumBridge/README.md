# Aurum PC Bridge

Aurum PC Bridge is the bootstrap control path between ChatGPT/Aurum and an authorized physical Windows machine already connected to the BoxBrain repository through a self-hosted GitHub Actions runner.

The bridge deliberately exposes capabilities instead of a general remote shell. A job is a small JSON object committed under `Projects/AurumBridge/jobs/`. The self-hosted Windows runner executes only an exact allowlist of read-only actions in `AurumBridge.ps1`, writes structured evidence under `Projects/AurumBridge/results/`, and records a local processed-job sentinel under `%ProgramData%\Aurum\Bridge\processed` so a job is not silently replayed.

Current bootstrap actions are:

- `bridge_health`
- `inventory`
- `seed_status`
- `docker_status`
- `process_snapshot`
- `network_snapshot`
- `storage_snapshot`

There is intentionally no `shell`, `powershell`, `command`, `script`, or arbitrary executable action. The executor rejects those fields if they appear in a job. Consequential capabilities such as removable-media writes, reboot/boot selection, service modification, keyboard/mouse actuation, or firmware/storage changes must be added later as individually bounded operations with their own authority and evidence gates.

Example job:

```json
{
  "schema": "aurum-pc-bridge-job-v1",
  "id": "bridge-health-20260818-01",
  "action": "bridge_health"
}
```

The GitHub workflow is only triggered by pushes to `main` affecting the bridge job/executor paths. Result-only commits do not trigger another execution cycle.

## Local usage loop

`UsageLoop.ps1` adds an independent, model-free failure loop for ChatGPT/Codex/Work usage exhaustion. It stores local state under `%ProgramData%\Aurum\UsageLoop` when writable and falls back to `%LOCALAPPDATA%\Aurum\UsageLoop` otherwise.

The usage loop:

- accepts bounded `aurum-usage-event-v1` incident records;
- deduplicates incidents before they become another retry loop;
- scans only known local OpenAI/Codex log roots for bounded usage-limit signals;
- redacts likely credentials before preserving excerpts;
- records a local incident ledger and continuation signal;
- marks model access as limited while allowing deterministic local Aurum work to continue;
- preserves a pending support-report record without inventing server-side token or credit quantities;
- explicitly records the cost of building/operating the usage loop as mitigation overhead that can be correlated against authoritative OpenAI telemetry.

`Aurum Local Usage Loop` runs on the self-hosted Windows runner every five minutes as a low-cost failsafe and immediately when a usage-event file is committed under `Projects/AurumBridge/usage-events/`. New sanitized evidence is written to `Projects/AurumBridge/usage-results/`. The local scan itself uses no model calls.

The current support-mail transport remains separate from the local detector: the loop produces a deduplicated `report_pending` evidence record so an authorized Gmail/ChatGPT or future direct OAuth transport can append one incident to the existing support case instead of creating duplicate cases.

This is a bootstrap carrier. The same capability/job/evidence contract can later be transported over Aurum's native gate field, an authenticated relay, or an MCP/ChatGPT adapter without changing the physical capability boundary.
