# Aurum Adaptive Shell Constitution

Status: design constraint for future Aurum-generated human interfaces.

Aurum may adapt the interface around the human, but it must preserve a stable path back to the familiar.

## 1. Human constants

The following controls are landmarks. Aurum may restyle them, offer additional access paths, or let the user deliberately remap them, but it must not silently remove or unpredictably relocate every path to them:

- Home / launcher
- Back / previous context
- Search
- Settings
- Notifications / attention center
- App and workspace switcher
- Accessibility controls
- Session / power controls
- Recovery / safe layout
- User customization and adaptation lock

At least one familiar, documented route to each landmark must remain available. A permanent `Safe Layout` restores a predictable baseline without deleting the user's data or preferences.

## 2. Adaptive surface

Everything outside the human constants may be proposed as an adaptive surface, including:

- panel and dock placement
- shortcuts and contextual actions
- workspace and window layouts
- application grouping
- context menus
- clipboard and text-assistance behavior
- automation suggestions
- browser/editor/media emphasis
- notification filtering
- resource-performance profiles
- media, lighting, audio, capture and publishing controls

Adaptations are reversible, inspectable, bounded, and attributable to evidence.

## 3. Interface design influences

Aurum should learn principles rather than imitate a vendor shell:

- Windows: discoverability, launcher/search integration, broad device/app compatibility
- macOS: consistency, low-friction application flow, coherent visual hierarchy
- Linux: workspaces, composability, terminal/power-user access, transparent control
- phone/tablet systems: direct manipulation, gestures, page-stack navigation, quick controls, task-focused surfaces

The user may choose any mixture and may pin a preferred interaction pattern so adaptation happens around it instead of replacing it.

## 4. Context adaptation

Aurum may infer an activity context only from bounded operational evidence. One weak signal is not enough when the consequence is significant.

Examples:

### Gaming
Evidence can include full-screen rendering, controller activity, sustained frame generation, and a foreground game process. Proposed adaptations may prioritize latency-sensitive CPU/GPU work, high-refresh display paths, responsive input, and suppressible background work.

### Coding
Evidence can include editor + terminal + compiler/test activity, source-file interaction, and repeated clipboard operations. Proposed adaptations may emphasize editor/terminal/build state, coding-aware text correction, deterministic clipboard workflows, fast build/test access, and persistent workspaces.

### Research / web
Evidence can include browser-dominant foreground activity, many related tabs, downloads/references, and repeated capture/search actions. Proposed adaptations may emphasize browser/network responsiveness, tab/workspace organization, reference capture, and retrieval tools.

### Media / social
Evidence can include editing/capture applications, media files, music/light control, export activity, and publishing preparation. Proposed adaptations may emphasize media throughput, preview responsiveness, storage/export state, lighting/music controls, and user-approved publishing automations.

### General productivity
When confidence is low or signals are mixed, Aurum should prefer the stable general profile rather than force a specialized mode.

## 5. Evidence and confidence

- Context inference must expose the evidence it used.
- Confidence must be explicit and bounded.
- Mode switching should use hysteresis so the interface does not flap between modes.
- High-impact changes require stronger evidence than cosmetic changes.
- Repeated user overrides become learning evidence that the inferred adaptation was wrong or unwanted.
- The user can pin a mode, pin individual controls, or disable adaptation globally.

## 6. Resource adaptation

Resource policy is separate from visual layout. Detecting an activity does not itself grant authority to change CPU/GPU/network/display/storage behavior.

Resource adaptations must be:

- reversible
- bounded in duration or tied to an observable context
- constrained by thermal, power, reliability, and accessibility limits
- visible in Proof View
- restricted to previously authorized resource scopes
- automatically rolled back when evidence for the context disappears, unless the user pins the profile

Aurum must never disable security, privacy, recovery, or critical system services merely to improve benchmark performance.

## 7. User model

The user experience model should learn interaction preferences, not sensitive personal traits that are unnecessary for interface operation.

Useful local learning includes:

- preferred launcher/navigation style
- frequently paired applications
- preferred workspace layouts
- repeated shortcuts and sequences
- correction/undo patterns
- preferred density, font scale, gesture use, keyboard use and pointer behavior
- activity-specific resource preferences
- adaptations repeatedly accepted, reverted, or locked

The model should be local-first, exportable, resettable, and understandable through a human projection.

## 8. Adaptation lifecycle

The normal lifecycle is:

`observe -> infer context -> propose -> simulate -> verify constraints -> apply reversible adaptation -> observe result -> learn -> retain/revert`

Before Aurum gains authority to apply a class of adaptation, it should first demonstrate that class in simulation and Proof View.

## 9. Self-build rule

Do not hand-code a specialized UI solution when the reusable goal is for Aurum to learn the capability class.

For a new interface problem, prefer:

`semantic contract -> examples/constraints -> Aurum derives candidate -> isolated verification -> Proof View -> bounded promotion`

The shell is therefore expected to evolve as Aurum's interface and I/O capabilities grow, while the human constants remain stable.