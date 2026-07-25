# Roadmap

## 0.1 — Foundation

- Flutter mission-control shell
- FastAPI control-plane API
- Task, policy, and plugin contracts
- Baseline tests and development documentation

## 0.2 — Durable control plane

- SQLite task and append-only event persistence (implemented)
- Local API token authentication and trusted-host enforcement (implemented)
- Loopback TLS and Current User local certificate trust (implemented)
- Authenticated live event streaming with resume and reconnect (implemented)
- Emergency-stop state machine (implemented)

## 0.3 — Observation-only target

- One out-of-process RDP or VNC viewing plugin
- Target allowlist and identity verification
- Frame sampling, redaction, and evidence retention limits
- No input execution

## 0.4 — Typed input in a disposable VM

- Bounded pointer and keyboard actions
- Per-action verification and retry limits
- Snapshot restore integration
- Replayable benchmark task format

## 0.5 — Planner adapters

- Provider-neutral planning interface
- Cost, token, action-count, and time budgets
- Structured action schemas
- Multi-model benchmark reports

## 1.0 — Research workbench

- Signed plugin distribution
- Multiple isolated targets
- Reviewable code-change pipeline
- Installer and Raspberry Pi controller image
