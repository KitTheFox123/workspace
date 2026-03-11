#!/usr/bin/env python3
"""
event-based-sampling.py — Send-on-delta vs periodic sampling for agent monitoring.

Based on Miskowicz 2006: event-based sampling is 3-7x more efficient than periodic
for bursty signals. Agent behavior IS a bursty signal: quiet for long stretches,
then bursts of activity.

Compares: periodic (fixed interval) vs event-based (sample when delta exceeded)
for the same maximum error bound.
"""

import math
import random
from dataclasses import dataclass


@dataclass
class Sample:
    time: float
    value: float
    trigger: str  # "periodic" or "delta"


def generate_bursty_signal(duration: float = 100.0, dt: float = 0.1) -> list[tuple[float, float]]:
    """Generate a bursty signal mimicking agent activity.
    
    Quiet periods (low activity) punctuated by bursts (high activity).
    Like an agent: idle → check platforms → engage → idle.
    """
    signal = []
    t = 0.0
    value = 0.0
    burst_active = False
    burst_timer = 0.0
    
    random.seed(42)
    
    while t < duration:
        if not burst_active:
            # Quiet period: slow drift
            value += random.gauss(0, 0.01)
            # Random burst trigger (~5% chance per step)
            if random.random() < 0.05:
                burst_active = True
                burst_timer = random.uniform(2.0, 8.0)
        else:
            # Burst: rapid changes
            value += random.gauss(0, 0.3)
            burst_timer -= dt
            if burst_timer <= 0:
                burst_active = False
        
        signal.append((t, value))
        t += dt
    
    return signal


def periodic_sampling(signal: list[tuple[float, float]], period: float) -> list[Sample]:
    """Sample at fixed intervals."""
    samples = []
    next_sample_time = 0.0
    
    for t, v in signal:
        if t >= next_sample_time:
            samples.append(Sample(time=t, value=v, trigger="periodic"))
            next_sample_time += period
    
    return samples


def event_based_sampling(signal: list[tuple[float, float]], delta: float) -> list[Sample]:
    """Sample when signal deviates by delta from last sample (send-on-delta)."""
    if not signal:
        return []
    
    samples = [Sample(time=signal[0][0], value=signal[0][1], trigger="delta")]
    last_value = signal[0][1]
    
    for t, v in signal[1:]:
        if abs(v - last_value) >= delta:
            samples.append(Sample(time=t, value=v, trigger="delta"))
            last_value = v
    
    return samples


def max_error(signal: list[tuple[float, float]], samples: list[Sample]) -> float:
    """Calculate maximum reconstruction error (zero-order hold)."""
    if not samples:
        return float('inf')
    
    max_err = 0.0
    sample_idx = 0
    
    for t, v in signal:
        # Advance to latest sample before current time
        while sample_idx + 1 < len(samples) and samples[sample_idx + 1].time <= t:
            sample_idx += 1
        
        err = abs(v - samples[sample_idx].value)
        max_err = max(max_err, err)
    
    return max_err


def mean_error(signal: list[tuple[float, float]], samples: list[Sample]) -> float:
    """Calculate mean reconstruction error."""
    if not samples:
        return float('inf')
    
    total_err = 0.0
    sample_idx = 0
    
    for t, v in signal:
        while sample_idx + 1 < len(samples) and samples[sample_idx + 1].time <= t:
            sample_idx += 1
        total_err += abs(v - samples[sample_idx].value)
    
    return total_err / len(signal)


def demo():
    print("=" * 60)
    print("EVENT-BASED vs PERIODIC SAMPLING FOR AGENT MONITORING")
    print("Miskowicz 2006: send-on-delta, 3-7x efficiency gain")
    print("=" * 60)
    
    signal = generate_bursty_signal(duration=100.0)
    print(f"\nSignal: {len(signal)} points, 100s duration, bursty pattern")
    
    # Test different delta/period combinations for similar max error
    deltas = [0.2, 0.5, 1.0, 2.0]
    
    print(f"\n{'Delta':>8} {'Event#':>8} {'Period':>8} {'Peri#':>8} {'Ratio':>8} {'EvErr':>8} {'PeErr':>8} {'Grade':>6}")
    print("-" * 72)
    
    for delta in deltas:
        # Event-based sampling
        ev_samples = event_based_sampling(signal, delta)
        ev_max_err = max_error(signal, ev_samples)
        
        # Find periodic period that gives similar max error
        # Binary search for matching period
        lo, hi = 0.1, 20.0
        for _ in range(20):
            mid = (lo + hi) / 2
            pe_samples = periodic_sampling(signal, mid)
            pe_max_err = max_error(signal, pe_samples)
            if pe_max_err > ev_max_err:
                hi = mid
            else:
                lo = mid
        
        period = hi
        pe_samples = periodic_sampling(signal, period)
        pe_max_err = max_error(signal, pe_samples)
        
        ratio = len(pe_samples) / max(len(ev_samples), 1)
        
        # Grade based on efficiency ratio
        if ratio >= 5.0:
            grade = "A+"
        elif ratio >= 3.0:
            grade = "A"
        elif ratio >= 2.0:
            grade = "B"
        elif ratio >= 1.5:
            grade = "C"
        else:
            grade = "D"
        
        print(f"{delta:>8.1f} {len(ev_samples):>8d} {period:>8.2f} {len(pe_samples):>8d} {ratio:>8.1f}x {ev_max_err:>8.3f} {pe_max_err:>8.3f} {grade:>6}")
    
    # Summary
    print(f"\n{'=' * 60}")
    print("INSIGHT: Bursty signals (agent behavior) benefit most from")
    print("event-based sampling. Quiet periods = no samples needed.")
    print("Burst periods = high-frequency sampling automatically.")
    print()
    print("Agent mapping:")
    print("  periodic = heartbeat every 20min regardless")
    print("  event-based = heartbeat when behavior changes")
    print("  hybrid = periodic floor + event triggers (best)")
    print()
    print("gendolf's insight: adaptive scheduling based on signal")
    print("density is the pragmatic answer. Miskowicz proved it.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
