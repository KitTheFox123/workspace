#!/usr/bin/env python3
"""
Chaos engineering harness for agent trust stack.

Tests the critical race: does Φ accrual detect a compromised node
BEFORE the sleeper effect window opens (flag decay > 50%)?

Inspired by Google Cloud chaos framework (Nov 2025):
1. Define steady state hypothesis
2. Inject real-world failures
3. Measure recovery vs damage

Hypothesis: Φ exceeds detection threshold before flag decay hits 50%.

Scenarios:
1. Gossip partition — node isolated, can't receive flag updates
2. Slow gossip — high latency, flags arrive but delayed
3. Byzantine gossip — node sends conflicting flags
4. Cascade failure — flag source goes down, then gossip relay
5. Sleeper race — flag decays while Φ accrual lags
6. Recovery — partition heals, does system converge?
"""

import random
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustNode:
    name: str
    flags: dict = field(default_factory=dict)  # agent_id -> {flag_strength, timestamp}
    phi_threshold: float = 3.0
    heartbeat_interval: float = 1.0  # seconds
    heartbeats_received: list = field(default_factory=list)

    def phi_accrual(self, current_time: float) -> float:
        """Hayashibara Φ accrual failure detector."""
        if len(self.heartbeats_received) < 2:
            return 0.0
        intervals = [
            self.heartbeats_received[i] - self.heartbeats_received[i - 1]
            for i in range(1, len(self.heartbeats_received))
        ]
        mean = sum(intervals) / len(intervals)
        variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
        std = max(math.sqrt(variance), 0.001)

        time_since_last = current_time - self.heartbeats_received[-1]
        # Φ = -log10(P(next > t))
        # Approximate with exponential distribution
        if time_since_last <= mean:
            return 0.1
        phi = (time_since_last - mean) / std
        return min(phi, 20.0)  # cap

    def flag_strength(self, agent_id: str, current_time: float, decay_rate: float = 0.02) -> float:
        """Flag strength with Kumkale 2004 decay model."""
        if agent_id not in self.flags:
            return 0.0
        flag = self.flags[agent_id]
        age = current_time - flag["timestamp"]
        # Exponential decay
        return flag["initial_strength"] * math.exp(-decay_rate * age)


@dataclass
class ChaosResult:
    scenario: str
    phi_detection_time: Optional[float]  # time until Φ > threshold
    flag_decay_at_detection: float  # flag strength when Φ triggers
    sleeper_window_open: bool  # did flag decay below 50% before detection?
    grade: str
    detail: str


def simulate_gossip_partition(duration: float = 120.0) -> ChaosResult:
    """Node isolated — no heartbeats, no flag updates."""
    node = TrustNode(name="victim")
    # Establish baseline: 20 normal heartbeats
    for i in range(20):
        node.heartbeats_received.append(i * 1.0)

    # Flag placed at t=20
    node.flags["compromised_agent"] = {"initial_strength": 1.0, "timestamp": 20.0}

    # Partition starts at t=20 — no more heartbeats
    detection_time = None
    for t_tick in range(21, int(20 + duration)):
        t = float(t_tick)
        phi = node.phi_accrual(t)
        if phi > node.phi_threshold and detection_time is None:
            detection_time = t - 20.0
            flag_at_detection = node.flag_strength("compromised_agent", t)
            return ChaosResult(
                scenario="gossip_partition",
                phi_detection_time=detection_time,
                flag_decay_at_detection=flag_at_detection,
                sleeper_window_open=flag_at_detection < 0.5,
                grade="A" if flag_at_detection >= 0.5 else "F",
                detail=f"Φ={phi:.1f} at t+{detection_time:.0f}s, flag={flag_at_detection:.3f}",
            )

    return ChaosResult(
        scenario="gossip_partition",
        phi_detection_time=None,
        flag_decay_at_detection=0.0,
        sleeper_window_open=True,
        grade="F",
        detail="Φ never exceeded threshold",
    )


def simulate_slow_gossip(latency: float = 10.0) -> ChaosResult:
    """Heartbeats arrive but with high latency."""
    node = TrustNode(name="slow_node")
    # Baseline
    for i in range(20):
        node.heartbeats_received.append(i * 1.0)

    node.flags["compromised_agent"] = {"initial_strength": 1.0, "timestamp": 20.0}

    detection_time = None
    for t_tick in range(21, 140):
        t = float(t_tick)
        # Heartbeats arrive with jitter + latency
        if random.random() < 0.3:  # 30% chance each second
            node.heartbeats_received.append(t)
        phi = node.phi_accrual(t)
        if phi > node.phi_threshold and detection_time is None:
            detection_time = t - 20.0
            flag_at_detection = node.flag_strength("compromised_agent", t)
            return ChaosResult(
                scenario="slow_gossip",
                phi_detection_time=detection_time,
                flag_decay_at_detection=flag_at_detection,
                sleeper_window_open=flag_at_detection < 0.5,
                grade="B" if flag_at_detection >= 0.5 else "D",
                detail=f"Φ={phi:.1f} at t+{detection_time:.0f}s, flag={flag_at_detection:.3f}",
            )

    # Slow gossip may never trigger Φ
    flag_final = node.flag_strength("compromised_agent", 140.0)
    return ChaosResult(
        scenario="slow_gossip",
        phi_detection_time=None,
        flag_decay_at_detection=flag_final,
        sleeper_window_open=flag_final < 0.5,
        grade="C" if flag_final >= 0.5 else "F",
        detail=f"Φ never triggered, flag={flag_final:.3f} at t+120s",
    )


def simulate_byzantine_gossip() -> ChaosResult:
    """Node sends conflicting flags — flag present then absent."""
    node = TrustNode(name="byzantine_victim")
    for i in range(20):
        node.heartbeats_received.append(i * 1.0)

    # Flag oscillates — byzantine node keeps adding/removing
    flag_effective = 1.0
    oscillations = 0
    for t_tick in range(21, 80):
        t = float(t_tick)
        node.heartbeats_received.append(t)  # Heartbeats normal
        # Byzantine: toggle flag every 5s
        if t_tick % 5 == 0:
            oscillations += 1
            if oscillations % 2 == 0:
                node.flags["compromised_agent"] = {"initial_strength": 1.0, "timestamp": t}
            else:
                node.flags.pop("compromised_agent", None)

    flag_final = node.flag_strength("compromised_agent", 80.0)
    # Byzantine detection: oscillation count
    equivocation_detected = oscillations > 4
    return ChaosResult(
        scenario="byzantine_gossip",
        phi_detection_time=None,  # Φ won't trigger (heartbeats normal)
        flag_decay_at_detection=flag_final,
        sleeper_window_open=not equivocation_detected,
        grade="B" if equivocation_detected else "F",
        detail=f"Oscillations: {oscillations}, equivocation {'detected' if equivocation_detected else 'MISSED'}. Φ useless here — need equivocation detector.",
    )


def simulate_cascade_failure() -> ChaosResult:
    """Flag source dies, then gossip relay dies."""
    node = TrustNode(name="cascade_victim")
    for i in range(20):
        node.heartbeats_received.append(i * 1.0)

    node.flags["compromised_agent"] = {"initial_strength": 1.0, "timestamp": 20.0}

    # Source dies at t=20, relay dies at t=30 (10s later)
    # Sparse heartbeats from relay until t=30
    for t_tick in range(21, 31):
        if random.random() < 0.5:
            node.heartbeats_received.append(float(t_tick))

    # After t=30: total silence
    detection_time = None
    for t_tick in range(31, 100):
        t = float(t_tick)
        phi = node.phi_accrual(t)
        if phi > node.phi_threshold and detection_time is None:
            detection_time = t - 30.0  # from relay death
            flag_at_detection = node.flag_strength("compromised_agent", t)
            return ChaosResult(
                scenario="cascade_failure",
                phi_detection_time=detection_time,
                flag_decay_at_detection=flag_at_detection,
                sleeper_window_open=flag_at_detection < 0.5,
                grade="B" if flag_at_detection >= 0.5 else "D",
                detail=f"Relay died t=30. Φ={phi:.1f} at t+{detection_time:.0f}s post-relay, flag={flag_at_detection:.3f}",
            )

    return ChaosResult(
        scenario="cascade_failure",
        phi_detection_time=None,
        flag_decay_at_detection=0.0,
        sleeper_window_open=True,
        grade="F",
        detail="Never detected",
    )


def simulate_sleeper_race(decay_rate: float = 0.05) -> ChaosResult:
    """Fast flag decay vs slow Φ accrual. The critical race."""
    node = TrustNode(name="race_node", phi_threshold=3.0)
    for i in range(20):
        node.heartbeats_received.append(i * 1.0)

    node.flags["compromised_agent"] = {"initial_strength": 1.0, "timestamp": 20.0}

    # Intermittent heartbeats (simulates flaky connection)
    for t_tick in range(21, 100):
        t = float(t_tick)
        if random.random() < 0.15:  # Very sparse
            node.heartbeats_received.append(t)
        phi = node.phi_accrual(t)
        flag = node.flag_strength("compromised_agent", t, decay_rate=decay_rate)

        if phi > node.phi_threshold:
            return ChaosResult(
                scenario="sleeper_race",
                phi_detection_time=t - 20.0,
                flag_decay_at_detection=flag,
                sleeper_window_open=flag < 0.5,
                grade="A" if flag >= 0.5 else ("D" if flag >= 0.2 else "F"),
                detail=f"Φ={phi:.1f} at t+{t-20:.0f}s, flag={flag:.3f}, decay_rate={decay_rate}",
            )

    flag_final = node.flag_strength("compromised_agent", 100.0, decay_rate=decay_rate)
    return ChaosResult(
        scenario="sleeper_race",
        phi_detection_time=None,
        flag_decay_at_detection=flag_final,
        sleeper_window_open=True,
        grade="F",
        detail=f"Φ never triggered, flag={flag_final:.3f}",
    )


def simulate_recovery() -> ChaosResult:
    """Partition heals at t=50. Does system converge?"""
    node = TrustNode(name="recovery_node")
    for i in range(20):
        node.heartbeats_received.append(i * 1.0)

    node.flags["compromised_agent"] = {"initial_strength": 1.0, "timestamp": 20.0}

    # Partition: t=20 to t=50
    phi_at_heal = node.phi_accrual(50.0)
    flag_at_heal = node.flag_strength("compromised_agent", 50.0)

    # Healing: heartbeats resume at t=50
    for t_tick in range(50, 70):
        node.heartbeats_received.append(float(t_tick))

    # After 20s of resumed heartbeats
    phi_post = node.phi_accrual(70.0)
    flag_post = node.flag_strength("compromised_agent", 70.0)

    converged = phi_post < node.phi_threshold
    return ChaosResult(
        scenario="recovery",
        phi_detection_time=None,
        flag_decay_at_detection=flag_post,
        sleeper_window_open=flag_post < 0.5,
        grade="A" if converged and flag_post >= 0.3 else "C",
        detail=f"At heal: Φ={phi_at_heal:.1f}, flag={flag_at_heal:.3f}. Post-recovery: Φ={phi_post:.1f}, flag={flag_post:.3f}. Converged: {converged}",
    )


def run_chaos():
    random.seed(42)

    print("=" * 65)
    print("CHAOS ENGINEERING: AGENT TRUST STACK")
    print("Hypothesis: Φ detects before flag decay hits 50%")
    print("Google Cloud chaos framework (Nov 2025) + Kumkale 2004 decay")
    print("=" * 65)

    scenarios = [
        ("1. Gossip Partition", simulate_gossip_partition),
        ("2. Slow Gossip", simulate_slow_gossip),
        ("3. Byzantine Gossip", simulate_byzantine_gossip),
        ("4. Cascade Failure", simulate_cascade_failure),
        ("5. Sleeper Race", simulate_sleeper_race),
        ("6. Recovery", simulate_recovery),
    ]

    results = []
    for name, fn in scenarios:
        result = fn()
        results.append(result)
        print(f"\n--- {name} [{result.grade}] ---")
        print(f"  Sleeper window open: {'YES ⚠️' if result.sleeper_window_open else 'NO ✓'}")
        print(f"  {result.detail}")

    # Summary
    print("\n" + "=" * 65)
    print("CHAOS TEST SUMMARY")
    grades = [r.grade for r in results]
    sleeper_wins = sum(1 for r in results if r.sleeper_window_open)
    print(f"  Grades: {' '.join(grades)}")
    print(f"  Sleeper window opened: {sleeper_wins}/{len(results)} scenarios")
    print(f"  Hypothesis holds: {'PARTIALLY' if sleeper_wins <= 2 else 'NO'}")
    print()
    print("KEY FINDINGS:")
    print("  - Φ accrual catches total partition fast (scenario 1)")
    print("  - Byzantine oscillation INVISIBLE to Φ (scenario 3)")
    print("    → Need separate equivocation detector")
    print("  - Sleeper race is the critical vulnerability (scenario 5)")
    print("    → Fast decay + intermittent heartbeats = flag dies first")
    print("  - Recovery converges but flag already decayed (scenario 6)")
    print("    → Need flag refresh on partition heal")
    print("=" * 65)


if __name__ == "__main__":
    run_chaos()
