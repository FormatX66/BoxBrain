# Integration Registry

Only discovered or explicitly planned boundaries are listed. Credentials are
never stored in this repository.

| Integration | Project | State | Boundary | Canonical documentation |
| --- | --- | --- | --- | --- |
| Flutter dashboard | BrainConnect | Implemented | Operator UI to authenticated controller API | [Development guide](https://github.com/FormatX66/BrainConnect/blob/main/docs/DEVELOPMENT.md) |
| FastAPI controller | BrainConnect | Implemented | Local control plane and audit API | [Controller README](https://github.com/FormatX66/BrainConnect/blob/main/controller/README.md) |
| SQLite | BrainConnect | Implemented | Durable task and append-only audit storage | [Architecture](https://github.com/FormatX66/BrainConnect/blob/main/docs/ARCHITECTURE.md) |
| Authenticated WebSocket | BrainConnect | Implemented | Resumable live audit delivery with no token in the URL | [Controller protocol](https://github.com/FormatX66/BrainConnect/blob/main/controller/README.md#live-event-protocol) |
| Target registry | BrainConnect | Implemented | Disabled-by-default identity records and enabled-target task admission | [Target protocol](https://github.com/FormatX66/BrainConnect/blob/main/docs/TARGETS.md) |
| FreeRDP observation | BrainConnect | Native helper, controller, Pi-loopback lab, and full Windows certificate gate verified | Fixed, out-of-process, certificate-pinned NLA/HYBRID RDP probe; no credentials or session | [Target protocol](https://github.com/FormatX66/BrainConnect/blob/main/docs/TARGETS.md) |
| FreeRDP pointer, keyboard, and bounded frame control | BrainConnect | Keyboard launch, visible text, and coordinate-click effects independently verified; connector installed inert | Exact endpoint, NLA/HYBRID, and certificate recheck; target-local credential binding; standard-session readiness; slow-path bounded pointer, button, text, key, sequence, and frame operations; all redirections disabled | [Open-lab control](https://github.com/FormatX66/BrainConnect/blob/main/docs/OPEN_LAB.md) |
| Pi controller service | BrainConnect | Deployed and verified | Immutable wheel and locked dependencies, unprivileged systemd unit, USB-bound API, private token and SQLite state | [Pi deployment](https://github.com/FormatX66/BrainConnect/blob/main/installer/pi/README.md) |
| Composite USB transport | BoxBrain edge agent | Source complete; live migration pending maintenance window | RNDIS `usb0` plus separate boot-protocol keyboard and mouse HID endpoints; disabled by default, alternate-access gate, timed rollback, and explicit commit | [Edge-agent USB HID](../edge/kali-pi-agent/README.md#headless-windows-keystroke-fallback) |
| Bluetooth HID transport | BoxBrain edge agent | Planned and intentionally disabled | Separate BlueZ pairing/trust boundary; USB insertion alone cannot authorize or accept a Bluetooth host | [Edge-agent boundary](../docs/EDGE_AGENT.md#headless-windows-keystroke-bootstrap) |
| Connection capability map | BoxBrain edge agent / controller / Flutter UI | Edge agent 0.13.0 deployed; controller/UI source complete, local rollout pending | Read-only per-transport state and proven dashboard, input, shell, data, video, and audio capability states | [Connection lifecycle](ConnectionLifecycle.md) |
| Near-field onboarding | BoxBrain edge agent | Contract defined; adapter not installed | Small identity/onboarding handoff to an IP or Bluetooth transport, never a repair session | [Connection lifecycle](ConnectionLifecycle.md#transport-roles) |
| GPT-assisted health assessment | BoxBrain / BrainConnect | Existing bounded diagnostics; unified lifecycle planned | Structured, secret-excluding inventory becomes repair proposals; no silent execution | [Health boundary](ConnectionLifecycle.md#health-assessment-boundary) |
| Hyper-V Windows lab | BrainConnect / BoxBrain | Installed, independently identified, registered, enabled, credential-rotated, and restored to `clean-linked-rotated-2026-07-29` | Generation 2 Windows 11 VM on Pi-only USB network; guarded UAC-gated credential rotation/checkpoint restore and no personal account or files | [Windows lab runbook](../sandbox/hyperv/README.md) |
| Restricted Windows SSH link | BoxBrain edge agent | Deployed and verified | Non-administrator, public-key-only target account; firewall source exactly `10.12.194.1`; no TTY or forwarding | [Edge-agent onboarding](../edge/kali-pi-agent/README.md) |
| Cloud model provider | BrainConnect | Planned | Provider-neutral structured planner adapter | [Roadmap](https://github.com/FormatX66/BrainConnect/blob/main/docs/ROADMAP.md) |
| Git hosting | Ecosystem | Configured | Existing BoxBrain remote plus private BrainConnect remote | [Repository index](../Admin/RepositoryIndex.md) |

Add integrations only after confirming the owning project and canonical
documentation.
