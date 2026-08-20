# Aurum Gen1: Everyone-OS Execution Plan

## Starting point

Gen0 has crossed the physical-machine proof boundary on Hopper: installed Aurum boots on real hardware, reaches the network, self-builds, updates its bounded runtime, models hardware, and has now rendered and accepted local input in a real full-screen graphical capability through Echo Rally.

Echo Rally is proof-of-concept ancestry, not the product surface. Its first-playable state remains preserved as an Easter egg while the proven graphics/input path becomes infrastructure for the real operating environment.

## Gen1 goal

**A normal person can sit down at an Aurum computer and accomplish everyday computing tasks without needing to understand Linux, shells, package managers, drivers, filesystems, bootloaders, or Aurum internals.**

Gen1 is not defined by a version number. It is earned when the capability set below is physically validated, recoverable, attributable, and reproducible on more than one authorized machine.

## Priority order

### 0. Preserve the known-good physical path

- Keep the working Hopper display/input route recoverable.
- Never replace the only known-good graphics/input state without a parallel tested candidate and rollback path.
- Preserve Echo Rally first-playable ancestry as a hidden Easter egg.

### 1. Generalize the physical graphics/input runtime into the Aurum shell

Use the exact path proven by Echo Rally to create a persistent local Aurum human surface.

Minimum shell capabilities:

- local display initialization
- keyboard and pointer input
- home/capability surface
- lightweight notifications/status
- network state
- settings/preferences
- recovery entry
- capability launcher/materializer
- secure user/session boundary

The shell is a phenotype, not the OS itself. It must be replaceable by user intent without forcing the machine-native substrate to imitate one desktop forever.

### 2. Replace "apps" with capability expression

Architectural capabilities are traits. `TR8` is a compact machine alias; `Trix` is an optional human-facing alias. Users may call them apps, programs, tools, skills, tricks, or anything else.

Initial everyday capability set:

- `TR8:WEB` — web access and browser-compatible experience
- `TR8:FILES` — human-compatible file/storage projection
- `TR8:MEDIA` — image/audio/video playback
- `TR8:WRITE` — text creation/editing
- `TR8:INTENT` — contextual intent assistance and adaptive language/input help
- `TR8:CONNECT` — Wi-Fi, Bluetooth, USB and device connectivity
- `TR8:RECOVER` — diagnosis, rollback, repair and known-good restoration

A trait may initially be materialized using conventional Linux software. The compatibility implementation is temporary; the semantic capability identity is durable.

### 3. Make the shell intent-first

The human should increasingly describe desired outcomes rather than administer software abstractions.

Examples:

- "I want to get online."
- "Open my pictures."
- "Make this work more like Windows."
- "Make this easier for my mom."
- "Help me spell this word."
- "Why is this computer slow?"

Aurum maps intent onto traits and constructs the needed user-facing phenotype.

### 4. Accessibility and adaptive assistance become foundational, not optional add-ons

Aurum should detect friction and help without making the person adapt to the computer first.

Core rules:

- help now; teach next when invited
- user owns language and final intent
- learn personal interaction patterns locally/private by default
- do not diagnose medical or learning conditions from behavior
- preserve unusual intentional language and personal voice
- make correction and assistance easily reversible

TypeTriX remains the Windows proving ground for portable `TR8:INTENT` behavior while Aurum gains the same capability natively.

### 5. Presence-adaptive resource behavior

Do not build normal-user sleep/hibernate/shutdown ceremony into the Gen1 UX.

Aurum remains logically present and contracts/expands resource use according to presence, workload, latency needs, thermal conditions, power source, background work and learned patterns. Physical power control remains recovery/maintenance/emergency behavior.

### 6. Strengthen self-building into generation selection

The unattended loop should evolve from simple update/build repetition into:

observe -> identify capability gap -> construct candidate -> validate beside known-good -> compare evidence -> select/reject -> checkpoint generation

Failed candidates remain useful evidence. Promotion requires attribution and rollback.

### 7. Continue adaptive driver synthesis in parallel

- model all observed devices
- compare current proven bound drivers with vendor/reference evidence
- synthesize exact-device behavioral contracts
- compile non-binding shadow implementations
- verify before any physical swap
- keep boot/storage/firmware/power-control domains gated until evidence is much stronger

The current Linux driver remains valid compatibility evidence, not a permanent architectural dependency.

### 8. Reproduce on a second physical node

Gen1 cannot be Hopper-only.

The seed must bring up a second authorized x86-64 machine with:

- boot/install/recovery
- network
- local graphical shell
- keyboard/pointer
- core everyday traits
- machine-specific hardware model
- unattended bounded self-building

Hopper-specific adaptations remain scoped unless broader evidence proves portability.

### 9. Begin native-substrate replacement under a usable system

Once users can already use Aurum, replace Linux-backed capabilities one domain at a time while preserving the compatibility fallback.

Suggested order:

1. low-risk local services/state
2. input/event plumbing
3. network/control services
4. audio/media paths
5. USB/Bluetooth/device lifecycle
6. graphics/display plumbing
7. native kernel services and scheduling/memory/IPC
8. storage and boot-critical paths last

## Gen1 completion gate

Gen1 is earned when all of the following are true:

- a nontechnical user can boot into a graphical Aurum environment and use it without a shell
- local keyboard/pointer and display are reliable
- core everyday traits can be expressed from intent
- web, writing, files/storage, media and connectivity are usable
- recovery can return to a known-good generation without specialist intervention
- unattended self-building can construct and validate candidates without destabilizing the live machine
- adaptive driver modeling runs continuously without unsafe automatic physical replacement
- user language, accessibility and learning assistance are adaptive
- presence-adaptive resource behavior replaces normal sleep/shutdown ceremony
- the same seed has produced a usable Aurum phenotype on at least one second physical machine
- every consequential state change remains attributable and recoverable

## North-star test

For every proposed feature, ask:

1. What underlying capability does the user actually need?
2. Which human abstraction can be treated as a projection instead of a permanent dependency?
3. Can Aurum learn or materialize this from stable machine semantics and evidence?
4. Does the change preserve user agency, recoverability and provenance?
5. Does it move Aurum closer to working for more people rather than only this one machine?

**Preserve meaning, evidence and capability. Everything else is negotiable.**
