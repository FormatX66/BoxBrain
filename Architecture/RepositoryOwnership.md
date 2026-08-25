# Repository and Service Ownership

## Purpose

This document separates physical products, persistent services, shared user
surfaces, website ownership, and source repositories. Similar code or a shared
console does not make two lifecycle roles the same product.

## BoxBrain and BrainConnect

### BoxBrain

**BoxBrain is the Raspberry Pi 4 field appliance.** It is brought to or
connected with a computer or other supported system so it can:

- discover and identify the system;
- establish bounded USB, Ethernet, Wi-Fi, Bluetooth, display, input, and other
  available transports;
- analyze system and hardware state;
- control the system through authorized capabilities;
- diagnose and repair it while preserving recovery evidence;
- provision and verify an appropriate longer-lived management route.

BoxBrain owns the initial physical connection, immediate diagnosis/repair
lifecycle, transport truth, and recovery boundary.

### BrainConnect

**BrainConnect is the persistent remote-management service that BoxBrain sets
up for the system's future care.** Once enrolled and independently verified,
BrainConnect provides the continuing remote observation, management,
maintenance, and repair route without requiring BoxBrain to remain physically
attached.

BoxBrain therefore establishes and proves BrainConnect; BrainConnect services
the enrolled system afterward. A BrainConnect route must remain disabled or
bounded until target identity, credentials, permissions, health, and rollback
requirements are satisfied.

### One shared console

BoxBrain and BrainConnect use the **same operator console experience**. The
console is a shared surface over two carriers:

```text
shared console
  -> BoxBrain route: attached discovery, analysis, control, and repair
  -> BrainConnect route: enrolled persistent remote management
```

The console must always show which carrier is active, what target identity was
verified, which capabilities are available, and whether an action is local,
attached, or remote. Sharing the console does not merge authority, credentials,
transport state, or lifecycle ownership.

The implementation should converge on one console contract and reusable UI
components instead of maintaining divergent BoxBrain and BrainConnect console
forks.

## ClusterSites

**ClusterSites is the canonical home for every hosted website and every website
build/deployment flow.** This includes, at minimum:

- Ubercorp;
- MadMorrigan;
- Arkmatx;
- XanderZombie;
- Wet Beard;
- WitchDicks;
- later hosted sites added to the cluster.

ClusterSites owns site source, shared components, asset/build policy, host and
domain mapping, validation, deployment planning, and site-specific release
adapters. A separate site repository may temporarily remain as a legacy mirror
or deployment carrier, but it is not an independent source of truth. New site
work lands in ClusterSites.

Before a legacy site repository is archived, ClusterSites must prove source,
asset, configuration, and deployment parity without deleting live host-only
secrets or state.

## Arkmatx.com

**Arkmatx.com is the technology-project web portal.** It exposes human-facing
pages, dashboards, callbacks, webhooks, and service entry points for projects
such as Aurum and other technical systems.

The Arkmatx website and its build/deployment flow belong to ClusterSites.
Specialized backend services may remain in their own repositories when they
have an independent runtime or security boundary—for example a Git webhook
bridge, quantum experiment gateway, or remote-management service. ClusterSites
owns how those services are represented and connected through Arkmatx.com; it
does not need to absorb their internal implementation.

`Web/Aurum-Arkmatx` in BoxBrain is an integration/evidence mirror. The
canonical website implementation belongs to ClusterSites. `arkmatx-deploy` may
remain a specialized portal/control-plane service, but any general website
source or site-build logic in it should migrate to ClusterSites.

## HeX-Control

HeX-Control was a learning scaffold with no remaining unique product
responsibility identified. Its apparent direction was superseded by
BrainConnect.

It was archived on 2026-08-25 after a final read-only check found no releases,
issues, consumers, or unique product implementation on `main`. GitHub retains
both repository branches and the deliberately unmerged `DO NOT MERGE` Chat-to-
Git bootstrap pull request as inert historical evidence. Do not reactivate or
merge that scaffold into BrainConnect unless a new requirement first proves a
unique capability that is not already owned elsewhere.

## Consolidation rules

1. Consolidate ownership before moving files.
2. Preserve provenance and Last Known Good deployment evidence.
3. Do not maintain two editable sources for one website or shared console.
4. Keep a separate repository when its runtime, release, credential, or
   security boundary is genuinely independent.
5. Archive superseded repositories only after unique-state and live-deployment
   parity checks.
6. Links and versioned contracts replace copied cross-repository source.

