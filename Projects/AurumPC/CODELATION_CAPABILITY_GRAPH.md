# Aurum Canonical Concept: Codelation Capability Graph

Status: **canonical architecture principle**

## Core idea

Aurum should not organize the machine primarily around human device names, conventional protocols, or the intended use of components.

Instead, Aurum should model both external and internal hardware as a graph of **capabilities and state transitions**.

The primary question is not:

> What is this device supposed to do?

It is:

> What state can this component sense, store, transform, transmit, actuate, or preserve, and what is the simplest reliable way to use that capability to reach the desired state?

## Codelation rule

Before inventing a new mechanism or depending on a conventional protocol, Aurum should:

1. Identify the desired state change or information transfer.
2. Inventory the physical and logical capabilities currently available.
3. Rank candidate paths by reliability, simplicity, latency, energy cost, reversibility, and safety.
4. Prefer the simplest bounded path that can cause the desired state change.
5. Re-evaluate when the environment changes.

Protocols remain implementation details where physics requires them, but they should not define the top-level machine model.

## External hardware as capabilities

Examples:

- Mouse / touchpad: HID event generator, wake actuator, human input sensor.
- Speaker: pressure-wave actuator, acoustic transmitter, alert device.
- Microphone: pressure-wave sensor, acoustic receiver, environmental sensor.
- Display: light emitter, pixel-state output surface, potential optical signaling channel.
- Camera / light sensor: optical receiver and environmental sensor.
- USB: power path, bidirectional data carrier, HID path, storage path, network path, recovery path.
- Ethernet / Wi-Fi / Bluetooth: radio or electrical data carriers rather than special-purpose abstractions.
- HDMI / display links: high-bandwidth state carriers in addition to human-visible video.
- Storage media: persistent state surface, identity carrier, transfer medium, recovery medium.
- Nearby authorized Bluetooth audio devices: opportunistic borrowed microphones/speakers when local transducers are unavailable.

The same desired transition may be reachable through very different channels. Example: waking a sleeping PC may be easier and more reliable through a 1-pixel USB HID mouse movement than through Wake-on-LAN.

## Internal hardware as capabilities

Aurum should apply the same reasoning inside the machine.

Instead of treating CPU, GPU, RAM, SSD, fan, battery controller, embedded controller, buses, sensors, and security hardware as isolated named components, map them into capabilities such as:

- compute
- parallel compute
- volatile state
- persistent state
- low-latency state
- transport
- sensing
- actuation
- timing
- power management
- thermal management
- identity / trust
- watchdog / recovery
- low-power always-on execution

Examples:

- CPU: deterministic general compute, control, sequencing.
- GPU: massively parallel compute plus high-bandwidth local memory, not merely graphics.
- RAM: fast mutable state surface, not merely 'memory'.
- caches: ultra-low-latency transient state.
- NVMe / SSD: persistent state surface with its own controller and timing characteristics.
- PCIe / USB / internal buses: transport fabrics.
- temperature sensors: internal environmental state sensors.
- fans: actuators with RPM feedback, not merely cooling appliances.
- battery / PMIC: power-state sensing and actuation.
- embedded controller: low-power observer/actuator for lid, buttons, charging, fans, sleep/wake and other machine states.
- TPM / secure elements: identity, attestation, trust and sealed-state primitives.
- clocks, performance counters, interrupts and watchdogs: timing and health-observation resources.

## Machine-native resource selection

Aurum should increasingly describe requirements rather than hard-code human storage/compute categories.

Example state requirement:

> Needs sub-millisecond access, may disappear on power loss, local to this processor, approximately 12 MB.

Aurum then selects an appropriate resource rather than beginning with 'put this in RAM.'

Example compute requirement:

> Needs tens of thousands of similar operations with loose ordering.

Aurum may select GPU or another parallel engine.

Example control requirement:

> Needs deterministic low-latency sequencing.

Aurum may select CPU or another suitable controller.

Example continuity requirement:

> Must remain available while the main OS sleeps.

Aurum may select an embedded controller, low-power subsystem, peer node, or other always-on path when available.

## Slush / StateWeave relationship

This concept complements Slush and StateWeave.

Human operating systems strongly separate RAM, cache, disk, buffers, network state and other storage classes. Aurum should be able to reason about them using properties instead:

- capacity
- persistence
- latency
- bandwidth
- locality
- reliability
- energy cost
- accessibility
- trust level

StateWeave can then place and move state according to machine requirements rather than human category names.

## Node-to-node application

The same capability graph extends beyond one motherboard.

Aurum nodes should be able to use one another as sensors, actuators, relays, recovery peers and alternate communication paths.

Examples already explored:

- Main PC node -> USB/SSH -> Pi4 BoxBrain node -> LAN -> Hopper node.
- Pi4 -> USB HID mouse movement -> wake main PC.
- Pi4 -> Wake-on-LAN -> fallback wake path.
- Speaker -> air -> microphone -> acoustic SOS / discovery channel.
- Bluetooth phone/headset/speaker -> borrowed acoustic transducer when local audio hardware is unavailable.

The key abstraction is not 'networking'. It is **state transfer across any available coupled path**.

## Safety boundary

Capability does not imply permission.

Aurum should observe aggressively but manipulate cautiously around:

- firmware flashing
- voltage rails and clock limits
- thermal limits
- battery charging controls
- TPM / secure-state changes
- destructive storage commands
- raw bus writes
- power cycling
- command-bearing out-of-band channels

Prefer reversible, bounded, measurable actions first. Escalate only when lower-risk paths fail.

## Canonical heuristic

> Do not ask what the hardware was meant for. Ask what state it can carry, sense, preserve, transform, or change.

This is a core Aurum architecture principle and a primary expression of codelation.
