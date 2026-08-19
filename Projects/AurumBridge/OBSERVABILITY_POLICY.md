# Aurum Observability Policy

Status: authoritative default for Aurum/BoxBrain observation and preflight.

## Principle

Prefer the lowest-codelation, most machine-native source of truth that can answer the question.

Aurum must not render/capture/interpret the desktop when structured machine state is already sufficient.

## Observation hierarchy

Use the first level that can answer the question with adequate confidence:

1. **Direct machine state**
   - process/service state
   - device and storage metadata
   - kernel/OS/hardware telemetry
   - filesystem contents and hashes
   - environment/runtime state
   - structured application state exposed locally

2. **Control-plane/API state**
   - GitHub runner/workflow/job state
   - repository receipts/artifacts/checksums
   - Docker/container state
   - network/API responses
   - durable bridge results

3. **Event/log state**
   - Windows event logs
   - application logs
   - runner diagnostics
   - build/test logs
   - bounded trace output

4. **Interactive-session metadata**
   - active user/session
   - foreground process/window identity
   - window title/class/process mapping
   - accessibility/UI automation tree when needed

5. **Targeted visual observation**
   - capture only the specific window/region needed if a nonvisual path cannot resolve the state

6. **Full desktop capture**
   - last-resort codelation only
   - on-demand, explicit, auditable, never the default monitoring channel

## Preflight rule

Before requesting or taking a screenshot, Aurum must preflight whether the missing fact can be obtained from a lower level in the hierarchy.

A screenshot is justified only when:

- the required state is genuinely visual,
- lower-codelation sources are unavailable, incomplete, contradictory, or insufficient,
- and the visual result materially changes the next action.

## Efficiency rule

Observation cost is part of planning. Aurum should minimize unnecessary translation, rendering, image capture, OCR, and human-facing representation when raw machine state is available.

## Privacy and retention

Visual capture should be request-scoped, minimized to the needed region where practical, hashed/receipted when consequential, and not retained longer than needed for the task.

## Human role

The user should not be required to photograph a monitor when Aurum can obtain the relevant state directly. Human visual input is a fallback for gaps in machine observability, not a normal control path.
