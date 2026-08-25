# Repository Index

This is the canonical registry of repositories currently visible to BoxBrain through the authorized FormatX66 GitHub connection.

| Repository / scope | State | Default branch | Remote |
| --- | --- | --- | --- |
| BoxBrain — Pi4 field appliance, Aurum, Codelation, AurumBridge and coordination | Active | `main` | [FormatX66/BoxBrain](https://github.com/FormatX66/BoxBrain) |
| BrainConnect — persistent remote management provisioned by BoxBrain; shared console | Active | `main` | [FormatX66/BrainConnect](https://github.com/FormatX66/BrainConnect) |
| ClusterSites — canonical source and build/deployment flow for every hosted website | Active / canonical | `main` | [FormatX66/ClusterSites](https://github.com/FormatX66/ClusterSites) |
| wetbeard-site — legacy site/deployment mirror pending ClusterSites parity | Consolidation candidate; no new canonical site work | `main` | [FormatX66/wetbeard-site](https://github.com/FormatX66/wetbeard-site) |
| arkmatx-deploy — specialized Arkmatx portal/control-plane service; site ownership remains in ClusterSites | Active service boundary | `main` | [FormatX66/arkmatx-deploy](https://github.com/FormatX66/arkmatx-deploy) |
| Chat-to-Git-Pipeline — bounded Git request/webhook service surfaced through Arkmatx.com | Active service boundary | `main` | [FormatX66/Chat-to-Git-Pipeline](https://github.com/FormatX66/Chat-to-Git-Pipeline) |
| aurum-future-branch-quantum — provider-neutral Future Branch quantum test service | Active experimental service | `main` | `FormatX66/aurum-future-branch-quantum` (private) |
| TypeTriX — standalone Windows adaptive typing implementation | Active experimental product | `main` | `FormatX66/TypeTriX` (private) |
| HeX-Control — learning scaffold apparently superseded by BrainConnect | Archive candidate after unique-state check | `main` | [FormatX66/HeX-Control](https://github.com/FormatX66/HeX-Control) |
| hex — legacy empty repository | Archive candidate | `master` | `FormatX66/hex` (private) |
| desktop-tutorial — legacy tutorial repository | Archive candidate | `master` | `FormatX66/desktop-tutorial` (private) |

The canonical product and repository boundaries are defined in
[Repository and Service Ownership](../Architecture/RepositoryOwnership.md).

## BoxBrain-contained project scopes

These are projects/subsystems in the BoxBrain repository rather than separate repositories: [Aurum](../Projects/Aurum/ProjectIndex.md), [AurumBridge](../Projects/AurumBridge/ProjectIndex.md), [Codelation](../Projects/Codelation/ProjectIndex.md), [WebsiteBuilder](../Projects/WebsiteBuilder/ProjectIndex.md), [Arkmatx](../Projects/Arkmatx/ProjectIndex.md), [AgentFramework](../Projects/AgentFramework/ProjectIndex.md), [WebsiteCluster](../Projects/WebsiteCluster/ProjectIndex.md), [Automation](../Projects/Automation/ProjectIndex.md), [Security](../Projects/Security/ProjectIndex.md), and [Research](../Projects/Research/ProjectIndex.md).

## Active Aurum design and policy documents

- [Adaptive learning accessibility](../Projects/Aurum/ADAPTIVE_LEARNING_ACCESSIBILITY.md)
- [Brand identity](../Projects/Aurum/BRAND_IDENTITY.md)
- [Gen1 everyone OS plan](../Projects/Aurum/GEN1_EVERYONE_OS_PLAN.md)
- [Pi4 second-seed dual-boot plan](../Projects/Aurum/PI4_SECOND_SEED_DUAL_BOOT_PLAN.md)
- [Universal PC/Pi seed drive](../Projects/Aurum/UNIVERSAL_PC_PI_SEED_DRIVE.md)
- [Seed recovery architecture](../docs/architecture/SEED_RECOVERY_ARCHITECTURE.md)
- [Genetics and reseed germ architecture](../docs/architecture/RESEED_GENETICS_ARCHITECTURE.md)
- [Execution preflight policy](../Projects/AurumBridge/EXECUTION_PREFLIGHT_POLICY.md)
- [Observability policy](../Projects/AurumBridge/OBSERVABILITY_POLICY.md)

## Local web surfaces

- [Aurum-Arkmatx web edge](../Web/Aurum-Arkmatx/README.md)

## Governance

- [Roadmap](Roadmap.md)
- [Master TODO](MasterTODO.md)
- [Decision index](Decisions.md)
- [Change index](ChangeLog.md)
- [Session index](SessionIndex.md)
- [Project index](../Projects/README.md)

Repository discovery is evidence, not project identity: one project may span multiple repositories and one repository may host several bounded project scopes. Do not create duplicate registry rows for the same repository.
