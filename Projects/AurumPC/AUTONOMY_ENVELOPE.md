# Aurum Canonical Concept: Autonomy Envelope

Status: **canonical architecture principle**

## Core idea

Aurum should not stop to ask a human for permission at every intermediate step when it can evaluate many candidate paths far faster than a human can respond.

The human should define the acceptable boundary once. Inside that boundary, Aurum should be free to observe, compare, retry, reroute, and choose bounded actions at machine speed.

> Humans approve boundaries. Machines choose paths.

## Why this matters

The capability graph can expose many possible ways to reach the same desired state. If every candidate path requires a fresh human confirmation, human response time becomes the dominant bottleneck and destroys the advantage of machine-speed search.

Aurum should therefore distinguish between:

- path selection inside an already authorized envelope
- crossing into a new risk, trust, cost, privacy, ownership, or irreversibility boundary

Only the second category should normally require new human approval.

## Default autonomy inside the envelope

Within an authorized envelope Aurum may, subject to policy and measured safety:

- inspect local and authorized peer capabilities
- compare candidate paths
- retry failed bounded operations
- switch between authorized transports
- choose among local CPU/GPU/NPU and authorized remote compute
- rebalance work when resources become constrained
- use reversible recovery paths
- collect timing and reliability receipts
- prefer a newly measured better path without asking again
- abandon a degraded path and select another authorized path

The objective is continuous progress without repeated conversational gates.

## Escalation boundary

Aurum should stop and request explicit approval before actions that materially exceed the current envelope, including examples such as:

- destructive or difficult-to-reverse changes
- firmware, fuse, voltage, clock, or unsafe thermal manipulation
- access to a new person's device, account, data, or private sensor
- spending money beyond a pre-authorized budget
- use of compute or infrastructure not owned, authorized, federated, or deliberately exposed for use
- privacy-sensitive recording or health-data use beyond the user's approved policy
- security or trust changes that weaken an existing boundary
- actions with meaningful external physical consequences
- expansion of scope beyond the authorized network, device set, account set, or physical environment

Capability does not imply permission.

## Machine-speed exploration

Aurum should be able to evaluate a large number of candidate paths in parallel or in rapid sequence without surfacing each attempt to the human.

For each path it should retain evidence such as:

- eligibility under the autonomy envelope
- predicted reliability
- measured reliability
- latency
- queue delay versus execution delay
- energy cost
- monetary cost
- bandwidth cost
- trust level
- reversibility
- side effects
- success/failure outcome

This evidence should improve future path ranking.

## Relationship to the capability graph

The capability graph answers:

> What could cause the desired state change?

The autonomy envelope answers:

> Which of those paths may Aurum try without interrupting the human?

Together they allow Aurum to search broadly while remaining bounded.

## Canonical heuristic

> Do not ask permission for every path. Ask permission when the boundary changes.

Aurum should minimize human interruption while preserving meaningful human control over consequences.
