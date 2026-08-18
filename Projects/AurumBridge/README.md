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

This is a bootstrap carrier. The same capability/job/evidence contract can later be transported over Aurum's native gate field, an authenticated relay, or an MCP/ChatGPT adapter without changing the physical capability boundary.
