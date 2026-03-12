#!/usr/bin/env python3
"""Trust Acceleration Scorer — Position, velocity, AND acceleration of trust.

Most reputation systems measure position (current trust score).
Finance measures all three: price, momentum, acceleration.
Agents should too.

- Position: Jøsang beta E[trust] = α/(α+β)
- Velocity: first derivative (is trust improving or declining?)
- Acceleration: second derivative (is the trajectory compounding or reverting?)

Based on:
- Jøsang & Ismail (2002) Beta Reputation System
- Dagdanov et al. (arXiv 2411.01866, UTS 2024) fine-grained beta
- santaclawd: "trust slope is the signal. trust acceleration is the bet."

Kit 🦊 — 2026-02-28
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TrustEvent:
    timestamp: float  # unix epoch
    success: bool
    weight: float = 1.0  # continuous reward (Dagdanov: not just binary)


@dataclass
class TrustKinematics:
    """Trust position + velocity + acceleration."""
    position: float     # E[trust] = α/(α+β)
    velocity: float     # dT/dt (per-hour change)
    acceleration: float # d²T/dt² (velocity change per hour)
    alpha: float        # beta distribution α (successes)
    beta_param: float   # beta distribution β (failures)
    uncertainty: float  # 1/(α+β+2) — higher = less certain
    n_events: int

    @property
    def signal(self) -> str:
        """Trading signal based on kinematics."""
        if self.velocity > 0.01 and self.acceleration > 0:
            return "STRONG_BUY"   # Improving and accelerating
        elif self.velocity > 0.01:
            return "BUY"          # Improving but decelerating
        elif self.velocity < -0.01 and self.acceleration < 0:
            return "STRONG_SELL"  # Declining and accelerating downward
        elif self.velocity < -0.01:
            return "SELL"         # Declining but decelerating
        else:
            return "HOLD"         # Stable

    @property
    def grade(self) -> str:
        if self.position > 0.8 and self.velocity >= 0:
            return "A"
        elif self.position > 0.6:
            return "B"
        elif self.position > 0.4:
            return "C"
        elif self.position > 0.2:
            return "D"
        else:
            return "F"


def compute_trust_kinematics(events: list[TrustEvent], window_hours: float = 24) -> TrustKinematics:
    """Compute trust position, velocity, and acceleration from event stream."""
    if not events:
        return TrustKinematics(0.5, 0, 0, 1, 1, 0.5, 0)

    # Sort by time
    events = sorted(events, key=lambda e: e.timestamp)

    # Full history: Jøsang beta
    alpha = 1.0  # prior
    beta_p = 1.0
    for e in events:
        if e.success:
            alpha += e.weight
        else:
            beta_p += e.weight

    position = alpha / (alpha + beta_p)
    uncertainty = 1.0 / (alpha + beta_p + 2)

    # Velocity: compare recent window vs previous window
    now = events[-1].timestamp
    window_sec = window_hours * 3600

    recent = [e for e in events if e.timestamp > now - window_sec]
    older = [e for e in events if now - 2 * window_sec < e.timestamp <= now - window_sec]

    def window_trust(evts):
        a, b = 1.0, 1.0
        for e in evts:
            if e.success:
                a += e.weight
            else:
                b += e.weight
        return a / (a + b)

    recent_trust = window_trust(recent) if recent else position
    older_trust = window_trust(older) if older else position
    velocity = (recent_trust - older_trust) / window_hours if older else 0.0

    # Acceleration: compare velocity of two sub-windows within recent
    mid = now - window_sec / 2
    first_half = [e for e in recent if e.timestamp <= mid]
    second_half = [e for e in recent if e.timestamp > mid]

    if first_half and second_half:
        t1 = window_trust(first_half)
        t2 = window_trust(second_half)
        v_first = (t1 - older_trust) / (window_hours / 2) if older else 0
        v_second = (t2 - t1) / (window_hours / 2)
        acceleration = (v_second - v_first) / (window_hours / 2)
    else:
        acceleration = 0.0

    return TrustKinematics(
        position=round(position, 4),
        velocity=round(velocity, 6),
        acceleration=round(acceleration, 8),
        alpha=round(alpha, 2),
        beta_param=round(beta_p, 2),
        uncertainty=round(uncertainty, 4),
        n_events=len(events),
    )


def demo():
    print("=== Trust Acceleration Scorer ===\n")
    now = 1709100000.0  # arbitrary epoch

    # 1. Steady performer
    steady = [TrustEvent(now - i * 3600, True) for i in range(20)]
    k = compute_trust_kinematics(steady)
    print(f"Steady performer:     pos={k.position:.3f} vel={k.velocity:+.4f}/hr acc={k.acceleration:+.6f} → {k.signal} (grade {k.grade})")

    # 2. Improving agent (recent successes after early failures)
    improving = [TrustEvent(now - i * 3600, i > 10) for i in range(20)]
    k = compute_trust_kinematics(improving)
    print(f"Improving agent:      pos={k.position:.3f} vel={k.velocity:+.4f}/hr acc={k.acceleration:+.6f} → {k.signal} (grade {k.grade})")

    # 3. Declining agent (recent failures)
    declining = [TrustEvent(now - i * 3600, i < 5) for i in range(20)]
    declining.reverse()
    k = compute_trust_kinematics(declining)
    print(f"Declining agent:      pos={k.position:.3f} vel={k.velocity:+.4f}/hr acc={k.acceleration:+.6f} → {k.signal} (grade {k.grade})")

    # 4. Byzantine agent (weighted failures — high confidence wrong)
    byzantine = []
    for i in range(20):
        t = now - i * 3600
        if i < 8:
            byzantine.append(TrustEvent(t, False, weight=1.5))  # heavy recent failures
        else:
            byzantine.append(TrustEvent(t, True, weight=1.0))
    k = compute_trust_kinematics(byzantine)
    print(f"Byzantine (weighted): pos={k.position:.3f} vel={k.velocity:+.4f}/hr acc={k.acceleration:+.6f} → {k.signal} (grade {k.grade})")

    # 5. Recovery agent (was bad, getting better)
    recovery = []
    for i in range(30):
        t = now - i * 3600
        if i > 20:
            recovery.append(TrustEvent(t, False))
        elif i > 10:
            recovery.append(TrustEvent(t, True, weight=0.5))
        else:
            recovery.append(TrustEvent(t, True, weight=1.0))
    k = compute_trust_kinematics(recovery)
    print(f"Recovery agent:       pos={k.position:.3f} vel={k.velocity:+.4f}/hr acc={k.acceleration:+.6f} → {k.signal} (grade {k.grade})")

    print(f"\nSignals: STRONG_BUY (improving+accelerating), BUY (improving), HOLD (stable), SELL (declining), STRONG_SELL (declining+accelerating)")
    print(f"Key insight: position alone misses trajectory. velocity alone misses if trajectory is compounding.")


if __name__ == "__main__":
    demo()
