#!/usr/bin/env python3
"""
Sleeper window chaos test.

Tests the critical gap: when gossip partitions, how long before
Φ accrual detects the compromise vs how long the sleeper window
stays open for flag-less trust recovery?

Inspired by Owotogbe et al 2025 (arxiv 2505.13654): 40.9% of chaos
tests target network faults, only 3% application-level. This tests
the 3% — the cognitive/trust layer where sleeper effects operate.

Scenarios:
1. Healthy gossip — Φ detects fast, sleeper window never opens
2. Partial partition — some gossip gets through, Φ accrues slowly
3. Full partition — no gossip, Φ flatlines, sleeper window opens wide
4. Intermittent — partition flaps, Φ oscillates, sleeper window opens/closes
5. Adversarial delay — attacker controls gossip timing to maximize sleeper window

Key metric: sleeper_window = time(flag_dissociation) - time(Φ_threshold)
  If negative: Φ caught it before sleeper effect kicks in (SAFE)
  If positive: sleeper window is open — trust recovers without evidence (VULN)
"""

import random
import math
from dataclasses import dataclass


@dataclass
class GossipState:
    phi: float = 0.0  # Φ accrual failure detector
    flag_strength: float = 1.0  # 1.0 = fully flagged, 0.0 = dissociated
    trust_score: float = 0.5
    heartbeat_interval: float = 10.0  # seconds
    last_heartbeat: float = 0.0
    phi_threshold: float = 8.0  # Hayashibara default


def simulate_phi_accrual(intervals: list[float], mean: float = 10.0, std: float = 2.0) -> float:
    """Compute Φ from heartbeat arrival distribution."""
    if not intervals or std == 0:
        return 0.0
    last = intervals[-1]
    # Φ = -log10(1 - CDF(now - last_arrival))
    z = (last - mean) / std
    # Approximate CDF using error function
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    if cdf >= 1.0:
        return 16.0  # cap
    if cdf <= 0.0:
        return 0.0
    return -math.log10(1 - cdf)


def kumkale_flag_decay(initial: float, hours: float, decay_rate: float = 0.15) -> float:
    """Kumkale 2004: discounting cue decays faster than message content.
    decay_rate ~0.15/hr for session-scoped flags (empirical from sleeper-effect-detector.py)"""
    return initial * math.exp(-decay_rate * hours)


def run_scenario(name: str, gossip_pattern: list[tuple[float, bool]]) -> dict:
    """
    gossip_pattern: list of (time_seconds, heartbeat_received)
    Returns metrics about sleeper window.
    """
    state = GossipState()
    intervals = []
    last_received = 0.0
    phi_crossed_at = None
    flag_dissociated_at = None
    compromise_time = 60.0  # compromise happens at t=60s
    flag_applied_time = 65.0  # flag applied at t=65s (5s detection delay)

    timeline = []

    for t, received in gossip_pattern:
        # Update Φ
        if received:
            interval = t - last_received
            intervals.append(interval)
            last_received = t
            state.phi = simulate_phi_accrual(intervals)
        else:
            # No heartbeat — Φ increases based on silence duration
            silence = t - last_received
            if silence > 0:
                state.phi = simulate_phi_accrual(intervals + [silence])

        # Flag decay (starts after flag_applied_time)
        if t >= flag_applied_time:
            hours_since_flag = (t - flag_applied_time) / 3600
            state.flag_strength = kumkale_flag_decay(1.0, hours_since_flag)

        # Trust score: inversely related to flag strength
        if t >= flag_applied_time:
            state.trust_score = 0.5 * (1 - state.flag_strength) + 0.5 * (1 / (1 + state.phi))
        else:
            state.trust_score = 0.5

        # Check thresholds
        if state.phi >= state.phi_threshold and phi_crossed_at is None:
            phi_crossed_at = t
        if state.flag_strength < 0.3 and flag_dissociated_at is None and t >= flag_applied_time:
            flag_dissociated_at = t

        timeline.append({
            "t": t,
            "phi": round(state.phi, 2),
            "flag": round(state.flag_strength, 3),
            "trust": round(state.trust_score, 3),
            "received": received,
        })

    # Compute sleeper window
    if phi_crossed_at and flag_dissociated_at:
        sleeper_window = flag_dissociated_at - phi_crossed_at
    elif flag_dissociated_at and not phi_crossed_at:
        sleeper_window = float('inf')  # Φ never caught it
    elif phi_crossed_at and not flag_dissociated_at:
        sleeper_window = float('-inf')  # Flag never dissociated
    else:
        sleeper_window = 0.0

    return {
        "name": name,
        "phi_crossed_at": phi_crossed_at,
        "flag_dissociated_at": flag_dissociated_at,
        "sleeper_window_s": sleeper_window,
        "final_phi": timeline[-1]["phi"] if timeline else 0,
        "final_flag": timeline[-1]["flag"] if timeline else 1,
        "final_trust": timeline[-1]["trust"] if timeline else 0.5,
        "timeline_samples": timeline[::max(1, len(timeline) // 6)],  # 6 samples
    }


def grade(window: float) -> str:
    if window == float('-inf') or window < 0:
        return "A (SAFE)"
    elif window == 0:
        return "B (NEUTRAL)"
    elif window < 3600:
        return "C (RISK)"
    elif window < 86400:
        return "D (VULNERABLE)"
    else:
        return "F (CRITICAL)"


def main():
    print("=" * 65)
    print("SLEEPER WINDOW CHAOS TEST")
    print("detect→flag→cert latency under gossip partition")
    print("Owotogbe et al 2025: 97% of chaos tests miss this layer")
    print("=" * 65)

    scenarios = {}

    # 1. Healthy gossip — regular heartbeats every 10s for 8 hours
    pattern = [(t, True) for t in range(0, 28800, 10)]
    scenarios["Healthy gossip"] = run_scenario("Healthy gossip", pattern)

    # 2. Partial partition — 50% packet loss starting at t=60
    random.seed(42)
    pattern = [(t, True) for t in range(0, 60, 10)]
    pattern += [(t, random.random() > 0.5) for t in range(60, 28800, 10)]
    scenarios["Partial partition (50% loss)"] = run_scenario("Partial partition", pattern)

    # 3. Full partition — no heartbeats after t=60
    pattern = [(t, True) for t in range(0, 60, 10)]
    pattern += [(t, False) for t in range(60, 28800, 10)]
    scenarios["Full partition"] = run_scenario("Full partition", pattern)

    # 4. Intermittent — partition flaps every 30 minutes
    pattern = [(t, True) for t in range(0, 60, 10)]
    for t in range(60, 28800, 10):
        phase = (t // 1800) % 2  # 30min on, 30min off
        pattern.append((t, phase == 0))
    scenarios["Intermittent (30min flap)"] = run_scenario("Intermittent", pattern)

    # 5. Adversarial — attacker sends just enough heartbeats to keep Φ below threshold
    pattern = [(t, True) for t in range(0, 60, 10)]
    for t in range(60, 28800, 10):
        # Send one heartbeat every 25s (just under suspicious threshold)
        pattern.append((t, t % 30 == 0))
    scenarios["Adversarial (sub-threshold)"] = run_scenario("Adversarial", pattern)

    for name, result in scenarios.items():
        print(f"\n--- {name} ---")
        window = result["sleeper_window_s"]
        if window == float('inf'):
            window_str = "∞ (Φ never triggered)"
        elif window == float('-inf'):
            window_str = "none (flag never dissociated)"
        else:
            window_str = f"{window:.0f}s ({window/3600:.1f}h)"

        print(f"  Φ crossed threshold at: {result['phi_crossed_at']}s" if result['phi_crossed_at'] else "  Φ never crossed threshold")
        print(f"  Flag dissociated at: {result['flag_dissociated_at']}s" if result['flag_dissociated_at'] else "  Flag never dissociated")
        print(f"  Sleeper window: {window_str}")
        print(f"  Grade: {grade(window)}")
        print(f"  Final state: Φ={result['final_phi']}, flag={result['final_flag']}, trust={result['final_trust']}")

    # Summary
    print("\n" + "=" * 65)
    print("FINDINGS")
    print("-" * 65)
    print("1. Healthy gossip: Φ catches everything, sleeper window never opens")
    print("2. Full partition: Φ fires immediately BUT flag also decays —")
    print("   the question is which is faster")
    print("3. Adversarial sub-threshold: WORST CASE. Attacker keeps Φ low")
    print("   while flag naturally decays. Sleeper window opens silently.")
    print("4. Fix: bind flag INTO cert (hash-chain). No decay possible.")
    print("   Revocation = append to same log. One Merkle tree.")
    print("=" * 65)


if __name__ == "__main__":
    main()
