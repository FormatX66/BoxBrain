# Integration Registry

Only discovered or explicitly planned boundaries are listed. Credentials are
never stored in this repository.

| Integration | Project | State | Boundary | Canonical documentation |
| --- | --- | --- | --- | --- |
| Flutter dashboard | BrainConnect | Implemented | Operator UI to authenticated controller API | [Development guide](../../BrainConnect/docs/DEVELOPMENT.md) |
| FastAPI controller | BrainConnect | Implemented | Local control plane and audit API | [Controller README](../../BrainConnect/controller/README.md) |
| SQLite | BrainConnect | Implemented | Durable task and append-only audit storage | [Architecture](../../BrainConnect/docs/ARCHITECTURE.md) |
| Authenticated WebSocket | BrainConnect | Implemented | Resumable live audit delivery with no token in the URL | [Controller protocol](../../BrainConnect/controller/README.md#live-event-protocol) |
| Target registry | BrainConnect | Implemented | Disabled-by-default identity records and enabled-target task admission | [Target protocol](../../BrainConnect/docs/TARGETS.md) |
| FreeRDP observation | BrainConnect | Native helper and authenticated controller deployed on the Kali Pi 4; live Windows lab pending | Fixed, out-of-process, certificate-pinned NLA/HYBRID RDP probe | [Native helper](../../BrainConnect/plugins/rdp-observer/native/README.md) |
| Pi controller service | BrainConnect | Deployed and verified | Immutable wheel and locked dependencies, unprivileged systemd unit, USB-bound API, private token and SQLite state | [Pi deployment](../../BrainConnect/installer/pi/README.md) |
| Cloud model provider | BrainConnect | Planned | Provider-neutral structured planner adapter | [Roadmap](../../BrainConnect/docs/ROADMAP.md) |
| Git hosting | Ecosystem | Configured | Existing BoxBrain remote plus private BrainConnect remote | [Repository index](../Admin/RepositoryIndex.md) |

Add integrations only after confirming the owning project and canonical
documentation.
