#!/usr/bin/env python3
"""Aurum experimental acoustic link primitives.

Phase 0/1 scope:
- generate short calibration sweeps and SOS beacons
- analyze recorded WAV files with Goertzel bins
- rank candidate carrier frequencies by simple SNR estimate
- keep the experiment read-only with respect to remote machines

This module intentionally avoids defining a full communications protocol.
It treats speaker/microphone hardware as generic actuator/sensor paths and
selects a usable acoustic carrier based on measured channel quality.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path
from typing import Iterable

SCHEMA = "aurum.acoustic-link.v0"
DEFAULT_RATE = 48000
DEFAULT_VOLUME = 0.12
DEFAULT_LOW = 12000
DEFAULT_HIGH = 20000
DEFAULT_STEP = 250
MAX_VOLUME = 0.25


def _clamp_volume(value: float) -> float:
    return max(0.0, min(float(value), MAX_VOLUME))


def _pcm16(samples: Iterable[float]) -> bytes:
    out = bytearray()
    for sample in samples:
        value = max(-1.0, min(1.0, float(sample)))
        out.extend(struct.pack("<h", int(round(value * 32767))))
    return bytes(out)


def tone(frequency: float, duration: float, *, rate: int, volume: float, phase: float = 0.0) -> list[float]:
    n = max(1, int(duration * rate))
    amp = _clamp_volume(volume)
    ramp = max(1, min(n // 2, int(rate * 0.005)))
    samples: list[float] = []
    for i in range(n):
        env = 1.0
        if i < ramp:
            env = 0.5 - 0.5 * math.cos(math.pi * i / ramp)
        elif i >= n - ramp:
            env = 0.5 - 0.5 * math.cos(math.pi * (n - 1 - i) / ramp)
        samples.append(amp * env * math.sin((2.0 * math.pi * frequency * i / rate) + phase))
    return samples


def silence(duration: float, *, rate: int) -> list[float]:
    return [0.0] * max(1, int(duration * rate))


def write_wav(path: Path, samples: Iterable[float], *, rate: int = DEFAULT_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(_pcm16(samples))


def make_sos(path: Path, *, frequency: float, rate: int = DEFAULT_RATE, volume: float = DEFAULT_VOLUME, unit: float = 0.09) -> dict:
    pattern = [1, 1, 1, 3, 3, 3, 1, 1, 1]
    samples: list[float] = []
    for index, length in enumerate(pattern):
        samples.extend(tone(frequency, unit * length, rate=rate, volume=volume))
        if index != len(pattern) - 1:
            samples.extend(silence(unit, rate=rate))
    write_wav(path, samples, rate=rate)
    return {
        "schema": SCHEMA,
        "kind": "sos-beacon",
        "frequency_hz": float(frequency),
        "sample_rate_hz": rate,
        "duration_s": len(samples) / rate,
        "volume_fraction": _clamp_volume(volume),
        "path": str(path),
    }


def frequency_candidates(low: int, high: int, step: int) -> list[int]:
    if step <= 0:
        raise ValueError("step must be positive")
    if low <= 0 or high <= low:
        raise ValueError("frequency range is invalid")
    return list(range(low, high + 1, step))


def make_sweep(path: Path, *, low: int = DEFAULT_LOW, high: int = DEFAULT_HIGH, step: int = DEFAULT_STEP, rate: int = DEFAULT_RATE, volume: float = DEFAULT_VOLUME, tone_s: float = 0.06, gap_s: float = 0.03) -> dict:
    candidates = [f for f in frequency_candidates(low, high, step) if f < rate / 2 - 50]
    if not candidates:
        raise ValueError("no candidate frequencies fit below Nyquist")
    samples: list[float] = []
    for frequency in candidates:
        samples.extend(tone(frequency, tone_s, rate=rate, volume=volume))
        samples.extend(silence(gap_s, rate=rate))
    write_wav(path, samples, rate=rate)
    return {
        "schema": SCHEMA,
        "kind": "calibration-sweep",
        "frequencies_hz": candidates,
        "sample_rate_hz": rate,
        "tone_s": tone_s,
        "gap_s": gap_s,
        "volume_fraction": _clamp_volume(volume),
        "path": str(path),
    }


def read_wav(path: Path) -> tuple[int, list[float]]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise ValueError("only 16-bit PCM WAV is supported in the first experiment")
    values = struct.unpack("<" + "h" * (len(frames) // 2), frames)
    if channels == 1:
        mono = [v / 32768.0 for v in values]
    else:
        mono = []
        for i in range(0, len(values), channels):
            mono.append(sum(values[i:i + channels]) / (32768.0 * channels))
    return rate, mono


def goertzel_power(samples: list[float], rate: int, frequency: float) -> float:
    if not samples:
        return 0.0
    omega = 2.0 * math.pi * frequency / rate
    coeff = 2.0 * math.cos(omega)
    s_prev = 0.0
    s_prev2 = 0.0
    for sample in samples:
        s = sample + coeff * s_prev - s_prev2
        s_prev2, s_prev = s_prev, s
    power = s_prev2 * s_prev2 + s_prev * s_prev - coeff * s_prev * s_prev2
    return max(0.0, power / (len(samples) * len(samples)))


def rank_channels(path: Path, *, low: int = DEFAULT_LOW, high: int = DEFAULT_HIGH, step: int = DEFAULT_STEP, neighbor_hz: int = 120, max_results: int = 12) -> dict:
    rate, samples = read_wav(path)
    candidates = [f for f in frequency_candidates(low, high, step) if f < rate / 2 - neighbor_hz - 10]
    rows = []
    for frequency in candidates:
        signal = goertzel_power(samples, rate, frequency)
        left = goertzel_power(samples, rate, max(20, frequency - neighbor_hz))
        right = goertzel_power(samples, rate, frequency + neighbor_hz)
        noise = max(1e-15, (left + right) / 2.0)
        snr_db = 10.0 * math.log10(max(signal, 1e-15) / noise)
        rows.append({"frequency_hz": frequency, "power": signal, "noise_power": noise, "snr_db": snr_db})
    rows.sort(key=lambda item: (item["snr_db"], item["power"]), reverse=True)
    best = rows[0] if rows else None
    return {
        "schema": SCHEMA,
        "kind": "channel-ranking",
        "input": str(path),
        "sample_rate_hz": rate,
        "best": best,
        "candidates": rows[:max_results],
        "interpretation": "Higher SNR is preferred. Re-test before use; laptop speaker/mic response can change with distance, orientation, room noise, and device power state.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aurum experimental adaptive acoustic link")
    sub = parser.add_subparsers(dest="command", required=True)

    sos = sub.add_parser("make-sos", help="Generate a short SOS beacon WAV")
    sos.add_argument("--out", type=Path, required=True)
    sos.add_argument("--frequency", type=float, default=18000.0)
    sos.add_argument("--rate", type=int, default=DEFAULT_RATE)
    sos.add_argument("--volume", type=float, default=DEFAULT_VOLUME)
    sos.add_argument("--unit", type=float, default=0.09)

    sweep = sub.add_parser("make-sweep", help="Generate a calibration sweep WAV")
    sweep.add_argument("--out", type=Path, required=True)
    sweep.add_argument("--low", type=int, default=DEFAULT_LOW)
    sweep.add_argument("--high", type=int, default=DEFAULT_HIGH)
    sweep.add_argument("--step", type=int, default=DEFAULT_STEP)
    sweep.add_argument("--rate", type=int, default=DEFAULT_RATE)
    sweep.add_argument("--volume", type=float, default=DEFAULT_VOLUME)
    sweep.add_argument("--tone-s", type=float, default=0.06)
    sweep.add_argument("--gap-s", type=float, default=0.03)

    rank = sub.add_parser("rank", help="Rank carrier frequencies in a recorded WAV")
    rank.add_argument("--input", type=Path, required=True)
    rank.add_argument("--low", type=int, default=DEFAULT_LOW)
    rank.add_argument("--high", type=int, default=DEFAULT_HIGH)
    rank.add_argument("--step", type=int, default=DEFAULT_STEP)
    rank.add_argument("--neighbor-hz", type=int, default=120)
    rank.add_argument("--max-results", type=int, default=12)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "make-sos":
        result = make_sos(args.out, frequency=args.frequency, rate=args.rate, volume=args.volume, unit=args.unit)
    elif args.command == "make-sweep":
        result = make_sweep(args.out, low=args.low, high=args.high, step=args.step, rate=args.rate, volume=args.volume, tone_s=args.tone_s, gap_s=args.gap_s)
    else:
        result = rank_channels(args.input, low=args.low, high=args.high, step=args.step, neighbor_hz=args.neighbor_hz, max_results=args.max_results)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
