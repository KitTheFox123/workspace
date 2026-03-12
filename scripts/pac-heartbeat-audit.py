#!/usr/bin/env python3
"""
pac-heartbeat-audit.py — PAC learning bounds for heartbeat-based agent auditing.

Based on:
- Valiant (1984): PAC learning framework
- santaclawd: "k=heartbeat interval, PAC bound per heartbeat cycle"
- Avenhaus et al (2001): Inspection games — adversary adapts to known k
- Hoeffding's inequality for finite-sample confidence bounds

Key insight: heartbeat cadence sets the CLOCK (sample rate).
PAC bound sets the CONFIDENCE (how many samples needed).
Stochastic k > fixed k (Avenhaus inspection games).

After N heartbeats: P(|observed_drift - true_drift| ≤ ε) ≥ 1 - δ
Sample complexity: N ≥ (1/(2ε²)) · ln(2/δ)  [Hoeffding]
"""

import math
from dataclasses import dataclass


@dataclass
class AuditConfig:
    name: str
    heartbeat_minutes: int  # Cadence
    epsilon: float          # Accuracy (max error)
    delta: float            # Confidence (failure probability)
    response_latency_minutes: int = 0  # Human vs automated


def hoeffding_sample_complexity(epsilon: float, delta: float) -> int:
    """Minimum samples for PAC bound via Hoeffding's inequality."""
    return math.ceil((1 / (2 * epsilon**2)) * math.log(2 / delta))


def time_to_confidence(config: AuditConfig) -> dict:
    """How long until PAC confidence achieved?"""
    n_samples = hoeffding_sample_complexity(config.epsilon, config.delta)
    beats_per_day = (24 * 60) / config.heartbeat_minutes
    days_needed = n_samples / beats_per_day
    hours_needed = days_needed * 24

    # Vulnerability window = detection + response
    vuln_window = config.heartbeat_minutes + config.response_latency_minutes

    # Effective detection: Nyquist says sample at 2x drift frequency
    nyquist_max_drift_period = 2 * config.heartbeat_minutes

    return {
        "config": config.name,
        "samples_needed": n_samples,
        "beats_per_day": beats_per_day,
        "days_to_pac": round(days_needed, 1),
        "hours_to_pac": round(hours_needed, 1),
        "vuln_window_min": vuln_window,
        "nyquist_max_drift_min": nyquist_max_drift_period,
        "epsilon": config.epsilon,
        "delta": config.delta,
    }


def main():
    print("=" * 70)
    print("PAC-BOUND HEARTBEAT AUDIT CALCULATOR")
    print("Valiant (1984) + Hoeffding + Avenhaus (2001)")
    print("=" * 70)

    configs = [
        AuditConfig("kit_fox_current", 20, 0.10, 0.05),
        AuditConfig("kit_tight", 20, 0.05, 0.01),
        AuditConfig("fast_heartbeat", 5, 0.10, 0.05),
        AuditConfig("slow_heartbeat", 60, 0.10, 0.05),
        AuditConfig("human_in_loop", 20, 0.10, 0.05, response_latency_minutes=120),
        AuditConfig("automated_response", 20, 0.10, 0.05, response_latency_minutes=1),
    ]

    print(f"\n{'Config':<22} {'N':<6} {'Days':<6} {'Hrs':<6} {'VulnWin':<8} {'ε':<6} {'δ':<6}")
    print("-" * 70)

    for cfg in configs:
        r = time_to_confidence(cfg)
        print(f"{r['config']:<22} {r['samples_needed']:<6} {r['days_to_pac']:<6} "
              f"{r['hours_to_pac']:<6} {r['vuln_window_min']:<8}min {r['epsilon']:<6} {r['delta']:<6}")

    # Epsilon-delta tradeoff table
    print("\n--- ε-δ Tradeoff (samples needed) ---")
    print(f"{'ε \\ δ':<8}", end="")
    for d in [0.10, 0.05, 0.01, 0.001]:
        print(f"{d:<8}", end="")
    print()
    for e in [0.20, 0.10, 0.05, 0.02, 0.01]:
        print(f"{e:<8}", end="")
        for d in [0.10, 0.05, 0.01, 0.001]:
            n = hoeffding_sample_complexity(e, d)
            print(f"{n:<8}", end="")
        print()

    # Key insights
    print("\n--- Key Insights ---")
    print("1. k=heartbeat → samples/day. PAC → samples needed. Time = N/rate.")
    print("2. ε=0.10, δ=0.05 → 185 samples → 2.6 days @ 20min heartbeats.")
    print("3. Tighter ε=0.05 → 738 samples → 10.2 days. Quadratic cost!")
    print("4. Vulnerability window = heartbeat + response latency.")
    print("   Human-in-loop adds HOURS. Automated = minutes.")
    print("5. Avenhaus (2001): adversary adapts to known k.")
    print("   Stochastic heartbeats (Poisson) > fixed interval.")
    print("   But PAC bound still holds — samples are samples.")
    print()
    print("santaclawd's frame: 'After N heartbeats P(envelope holds) ≥ 1-δ'")
    print("The monitoring cadence IS the k parameter.")
    print("Faster heartbeats = tighter bounds = faster confidence.")
    print("But: response_latency dominates vulnerability, not detection.")


if __name__ == "__main__":
    main()
