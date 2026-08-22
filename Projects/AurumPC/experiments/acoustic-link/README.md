# Aurum Experimental Lane: Adaptive Acoustic Link

Status: **experimental / discovery-only**

## Why this exists

Aurum should not assume that a speaker is "for sound" or that a microphone is "for speech."
They are an actuator and a sensor coupled through air. If normal network paths disappear,
the acoustic path may still carry useful machine state.

This lane is a direct application of the Aurum codelation principle:

> Start with the state change or information transfer that is needed. Then inspect every
> available physical/data path for the simplest reliable carrier, regardless of the
> channel's conventional human purpose.

## First proof

The first proof is intentionally small and measurable:

1. Node A emits a short calibration sweep.
2. Node B records it.
3. Node B measures candidate frequencies and ranks them by signal-to-noise ratio.
4. The nodes choose the clearest usable carrier.
5. Node A emits an SOS-style beacon (`... --- ...`) on that carrier.
6. Node B detects/records the beacon and produces a receipt containing:
   - selected frequency
   - SNR/confidence
   - sample rate
   - timestamps
   - eventual round-trip timing

No remote control command is authorized in this phase.

## Adaptive band selection

Do **not** hard-code "ultrasonic" as the answer.

Laptop speakers and microphones vary dramatically. Some roll off steeply above 15-17 kHz;
others may handle near-ultrasonic tones reasonably well. Rooms, fans, orientation, distance,
microphone processing, and power state all change the channel.

The intended search order is:

- near-ultrasonic / high-audible band when hardware supports it
- quieter high-frequency audible bands
- ordinary audible tones as a fallback

Aurum should measure first, choose the best channel, and re-calibrate when channel quality
falls below threshold.

The initial probe defaults to 12-20 kHz at a 48 kHz sample rate, but those are merely
experimental bounds.

## Opportunistic transducer scavenging

Aurum must not conclude that the acoustic lane is unavailable merely because the current
machine lacks a usable local speaker or microphone.

Instead, ask a more general question:

> What authorized nearby hardware can convert machine state into sound, or sound back into
> machine state?

Candidate transducers may include:

- paired Bluetooth headsets and earbuds
- paired phones or tablets that expose microphone/speaker capability
- Bluetooth speakers and soundbars
- TVs and monitors with audio output
- another laptop or desktop
- car audio or other known paired audio systems
- USB audio adapters or conference speakers

The device's intended human role is irrelevant. Aurum should rank endpoints by the capability
needed for the current state transition:

- **TX-capable**: can emit the chosen carrier clearly
- **RX-capable**: can capture the chosen carrier with useful SNR
- **duplex-capable**: can transmit and receive for acknowledgement/negotiation
- **availability**: currently powered, connected, and accessible
- **channel quality**: measured SNR / distortion / latency
- **trust**: already paired, explicitly authorized, or otherwise within the user's approved
  device set

Aurum may discover nearby devices, but it must not silently commandeer unknown third-party
phones, headsets, speakers, or microphones. Discovery is not authorization.

This allows a fallback chain such as:

`local speaker/mic -> paired headset -> paired phone -> nearby approved speaker/mic -> no acoustic path`

The chain should be dynamic. If a borrowed headset produces a cleaner 18.2 kHz path than the
laptop's own speakers, Aurum should prefer the headset. If the headset disappears, recalibrate
and choose another transducer.

## Timing

Timing is part of the experiment, not a cosmetic metric.

Record:

- T0: transmit intent created
- T1: playback begins
- T2: receiver first detects carrier
- T3: beacon fully decoded
- T4: acknowledgement begins
- T5: acknowledgement decoded

For borrowed Bluetooth transducers, also record:

- TD0: endpoint discovery begins
- TD1: candidate endpoint found
- TD2: authorized endpoint connected/selected
- TD3: audio path becomes usable

That separates discovery/pairing latency from the actual acoustic channel and from scheduler
or queue delay.

## Safety / trust boundary

- Keep calibration tones short and low amplitude.
- The prototype caps generated amplitude at 25% full scale.
- Acoustic discovery does not imply authorization.
- Bluetooth discovery does not imply permission to connect or use a device.
- A recorded sound can be replayed, so future command-bearing messages must use
  challenge/response or another authenticated freshness mechanism.
- Never treat "heard a valid SOS pattern" as permission to perform destructive actions.
- Respect the fact that microphones/speakers may be unavailable while a device sleeps.

## Current prototype

`aurum_acoustic_link.py` uses only the Python standard library.

Commands:

```text
python aurum_acoustic_link.py make-sweep --out calibration.wav
python aurum_acoustic_link.py make-sos --out sos.wav --frequency 18000
python aurum_acoustic_link.py rank --input recorded.wav
```

The analyzer uses Goertzel bins so it can rank candidate carrier frequencies without NumPy.

This is intentionally **not a full modem** yet. The next proof should use two physical Aurum
nodes and measured speaker/microphone data before choosing FSK, chirps, OFDM, or another
encoding.

## Evidence gates

- **Defined:** experiment and safety boundary documented.
- **Executable:** WAV generation and channel-ranking prototype runs.
- **Tested (synthetic):** generated SOS WAV is correctly ranked at its injected carrier.
- **Physical acoustic proof:** pending.
- **Borrowed Bluetooth transducer discovery:** pending.
- **Borrowed authorized transducer acoustic proof:** pending.
- **Adaptive two-node acknowledgement:** pending.
- **Authenticated command channel:** future experiment, not yet authorized.
