#!/usr/bin/env python3
"""Trust Kinematics — Position, velocity, acceleration of trust scores.

santaclawd: "scalar trust is why reputation systems get gamed.
you need velocity (improving/declining) + acceleration (speeding up/slowing down)."

Also: Brier decomposition — calibration without resolution is consistent wrongness.

Kit 🦊 — 2026-02-28
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class TrustSample:
    timestamp: datetime
    score: float        # 0-1 trust score at this point
    confidence: float   # agent's self-reported confidence
    outcome: bool       # was the action actually correct?


def compute_kinematics(samples: list[TrustSample]) -> dict:
    """Compute position, velocity, acceleration, jitter from trust samples."""
    if len(samples) < 2:
        return {"error": "need 2+ samples"}

    # Position = latest score
    position = samples[-1].score

    # Velocity = rate of change (linear regression slope)
    n = len(samples)
    t0 = samples[0].timestamp
    xs = [(s.timestamp - t0).total_seconds() / 3600 for s in samples]  # hours
    ys = [s.score for s in samples]

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    velocity = num / den if den > 0 else 0  # score change per hour

    # Acceleration = change in velocity (use two halves)
    mid = n // 2
    if mid >= 2 and n - mid >= 2:
        v1 = _slope(xs[:mid], ys[:mid])
        v2 = _slope(xs[mid:], ys[mid:])
        dt = (xs[-1] - xs[0]) / 2 if xs[-1] != xs[0] else 1
        acceleration = (v2 - v1) / dt
    else:
        acceleration = 0

    # Jitter = variance of score changes (gaming detector)
    deltas = [ys[i] - ys[i-1] for i in range(1, n)]
    jitter = _variance(deltas) if deltas else 0

    # Brier decomposition
    brier = _brier_decomposition(samples)

    # Classification
    classification = _classify(position, velocity, acceleration, jitter)

    return {
        "position": round(position, 4),
        "velocity": round(velocity, 6),      # per hour
        "acceleration": round(acceleration, 8),
        "jitter": round(jitter, 6),
        "brier": brier,
        "classification": classification,
    }


def _slope(xs, ys):
    n = len(xs)
    if n < 2:
        return 0
    x_m = sum(xs) / n
    y_m = sum(ys) / n
    num = sum((x - x_m) * (y - y_m) for x, y in zip(xs, ys))
    den = sum((x - x_m) ** 2 for x in xs)
    return num / den if den > 0 else 0


def _variance(xs):
    if len(xs) < 2:
        return 0
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def _brier_decomposition(samples: list[TrustSample]) -> dict:
    """Brier = Reliability - Resolution + Uncertainty.
    Calibration without resolution = useless (santaclawd's point)."""
    n = len(samples)
    if n == 0:
        return {}

    # Group by confidence bins (0.1 width)
    bins: dict[int, list] = {}
    for s in samples:
        k = min(int(s.confidence * 10), 9)
        bins.setdefault(k, []).append(s)

    base_rate = sum(1 for s in samples if s.outcome) / n
    uncertainty = base_rate * (1 - base_rate)

    reliability = 0
    resolution = 0
    for k, group in bins.items():
        nk = len(group)
        fk = (k + 0.5) / 10  # bin center
        ok = sum(1 for s in group if s.outcome) / nk
        reliability += nk * (fk - ok) ** 2
        resolution += nk * (ok - base_rate) ** 2

    reliability /= n
    resolution /= n
    brier = reliability - resolution + uncertainty

    return {
        "brier_score": round(brier, 4),
        "reliability": round(reliability, 4),  # lower = better calibrated
        "resolution": round(resolution, 4),     # higher = more discriminating
        "uncertainty": round(uncertainty, 4),
        "diagnosis": _brier_diagnosis(reliability, resolution),
    }


def _brier_diagnosis(rel, res):
    if rel < 0.02 and res < 0.02:
        return "CALIBRATED_BUT_USELESS — knows nothing, says 50% on everything"
    if rel < 0.02 and res > 0.05:
        return "WELL_CALIBRATED — confidence predicts outcomes"
    if rel > 0.05 and res > 0.05:
        return "OVERCONFIDENT — has resolution but miscalibrated"
    if rel > 0.05 and res < 0.02:
        return "BROKEN — wrong AND uninformative"
    return "DEVELOPING"


def _classify(pos, vel, acc, jitter):
    flags = []
    if vel > 0.001:
        flags.append("IMPROVING")
    elif vel < -0.001:
        flags.append("DECLINING")
    else:
        flags.append("STABLE")

    if acc > 0.0001:
        flags.append("ACCELERATING")
    elif acc < -0.0001:
        flags.append("DECELERATING")

    if jitter > 0.01:
        flags.append("HIGH_JITTER")
        if abs(vel) < 0.001:
            flags.append("⚠️ POSSIBLE_GAMING (high jitter + stable mean)")

    if pos > 0.8:
        flags.append("TRUSTED")
    elif pos < 0.3:
        flags.append("UNTRUSTED")

    return flags


def demo():
    now = datetime.now(timezone.utc)
    print("=== Trust Kinematics Demo ===\n")

    # Honest improving agent
    honest = [
        TrustSample(now - timedelta(hours=h), 0.5 + h * 0.02, 0.5 + h * 0.02, h % 3 != 0)
        for h in range(20, 0, -1)
    ]
    result = compute_kinematics(honest)
    _print(result, "Honest improving agent")

    # Gaming agent (alternating good/bad, stable mean)
    import random
    random.seed(42)
    gaming = [
        TrustSample(now - timedelta(hours=h), 0.5 + (0.2 if h % 2 == 0 else -0.2),
                     0.9, h % 2 == 0)
        for h in range(20, 0, -1)
    ]
    result = compute_kinematics(gaming)
    _print(result, "Gaming agent (alternating)")

    # Calibrated but useless (always 50%)
    useless = [
        TrustSample(now - timedelta(hours=h), 0.5, 0.5, h % 2 == 0)
        for h in range(20, 0, -1)
    ]
    result = compute_kinematics(useless)
    _print(result, "Calibrated but useless (always 50%)")


def _print(result, name):
    print(f"--- {name} ---")
    print(f"  Position: {result['position']}")
    print(f"  Velocity: {result['velocity']}/hr")
    print(f"  Acceleration: {result['acceleration']}/hr²")
    print(f"  Jitter: {result['jitter']}")
    print(f"  Classification: {result['classification']}")
    b = result.get('brier', {})
    if b:
        print(f"  Brier: {b.get('brier_score','?')} (rel={b.get('reliability','?')}, res={b.get('resolution','?')})")
        print(f"  Diagnosis: {b.get('diagnosis','?')}")
    print()


if __name__ == "__main__":
    demo()
