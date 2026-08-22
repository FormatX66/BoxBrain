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

## Timing

Timing is part of the experiment, not a cosmetic metric.

Record:

- T0: transmit intent created
- T1: playback begins
- T2: receiver first detects carrier
- T3: beacon fully decoded
- T4: acknowledgement begins
- T5: acknowledgement decoded

That separates scheduler/queue delay from physical acoustic propagation and processing delay.

## Safety / trust boundary

- Keep calibration tones short and low amplitude.
- The prototype caps generated amplitude at 25% full scale.
- Acoustic discovery does not imply authorization.
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
- **Adaptive two-node acknowledgement:** pending.
- **Authenticated command channel:** future experiment, not yet authorized.
