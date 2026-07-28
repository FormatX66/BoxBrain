# Integration Registry

Only discovered or explicitly planned boundaries are listed. Credentials are
never stored in this repository.

| Integration | Project | State | Boundary | Canonical documentation |
| --- | --- | --- | --- | --- |
| Flutter dashboard | BrainConnect | Implemented | Operator UI to authenticated controller API | [Development guide](../../BrainConnect/docs/DEVELOPMENT.md) |
| FastAPI controller | BrainConnect | Implemented | Local control plane and audit API | [Controller README](../../BrainConnect/controller/README.md) |
| SQLite | BrainConnect | Implemented | Durable task and append-only audit storage | [Architecture](../../BrainConnect/docs/ARCHITECTURE.md) |
| RDP or VNC observation | BrainConnect | Planned | Out-of-process, observation-only plugin | [Plugin contract](../../BrainConnect/docs/PLUGIN_CONTRACT.md) |
| Cloud model provider | BrainConnect | Planned | Provider-neutral structured planner adapter | [Roadmap](../../BrainConnect/docs/ROADMAP.md) |
| Git hosting | Ecosystem | Unconfigured | Remote origin for each repository | [Repository index](../Admin/RepositoryIndex.md) |

Add integrations only after confirming the owning project and canonical
documentation.
