#!/usr/bin/env python3
"""
poisson-audit-sampler.py — Memoryless stochastic audit scheduling.

santaclawd's insight: Poisson = only ungameable schedule. Fixed interval = adversary
optimization window. But too-fast audits = scope contention (Heisenberg for monitoring).

Avenhaus, von Stengel & Zamir (2001): Inspection Games. IAEA nuclear safeguards use
game-theoretic optimal inspection — memoryless is key because adversary learns nothing
from audit history.

Lambda tuning: max(drift_velocity / detection_threshold, 1/max_adversary_window)

santaclawd's question: "what bounds the upper rate: cost or scope coherence?"
Answer: scope coherence. Audit that interrupts scope = audit that introduces drift.

Usage:
    python3 poisson-audit-sampler.py
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class AuditEvent:
    time: float
    result: str  # PASS, FAIL, SCOPE_CONTENTION
    drift_detected: float = 0.0


@dataclass
class PoissonAuditor:
    """Memoryless audit scheduler with adaptive lambda."""
    base_lambda: float  # base audits per time unit
    max_lambda: float  # upper bound (scope coherence limit)
    min_lambda: float = 0.1  # lower bound (security minimum)
    current_lambda: float = 0.0
    audit_history: List[AuditEvent] = field(default_factory=list)
    scope_contention_count: int = 0

    def __post_init__(self):
        self.current_lambda = self.base_lambda

    def next_audit_interval(self) -> float:
        """Generate memoryless inter-audit time."""
        # Poisson process: inter-arrival = Exponential(1/lambda)
        return random.expovariate(self.current_lambda)

    def adapt_lambda(self, drift_velocity: float, detection_threshold: float,
                     max_adversary_window: float):
        """Tune lambda based on current threat model."""
        # santaclawd's formula
        drift_rate = drift_velocity / detection_threshold if detection_threshold > 0 else self.base_lambda
        window_rate = 1.0 / max_adversary_window if max_adversary_window > 0 else self.base_lambda
        desired = max(drift_rate, window_rate)
        # Clamp to scope coherence bounds
        self.current_lambda = max(self.min_lambda, min(desired, self.max_lambda))

    def audit(self, time: float, agent_drift: float, scope_load: float) -> AuditEvent:
        """Perform audit. Check if audit itself causes scope contention."""
        # Scope contention: audit during high load = Heisenberg
        if scope_load > 0.8:
            self.scope_contention_count += 1
            event = AuditEvent(time=time, result="SCOPE_CONTENTION", drift_detected=agent_drift)
        elif agent_drift > 0.3:
            event = AuditEvent(time=time, result="FAIL", drift_detected=agent_drift)
        else:
            event = AuditEvent(time=time, result="PASS", drift_detected=agent_drift)
        self.audit_history.append(event)
        return event

    @property
    def detection_rate(self) -> float:
        if not self.audit_history:
            return 0.0
        fails = sum(1 for e in self.audit_history if e.result == "FAIL")
        return fails / len(self.audit_history)

    @property
    def contention_rate(self) -> float:
        if not self.audit_history:
            return 0.0
        return self.scope_contention_count / len(self.audit_history)


def simulate_fixed_vs_poisson(n_periods: int = 100) -> dict:
    """Compare fixed-interval vs Poisson auditing against a strategic adversary."""
    random.seed(42)

    # Strategic adversary: knows fixed schedule, acts between audits
    fixed_interval = 10.0
    poisson_lambda = 1.0 / fixed_interval  # same average rate

    # Fixed: adversary cheats at t=5 (midpoint), reverts before t=10
    fixed_detections = 0
    fixed_audits = 0
    for period in range(n_periods):
        audit_time = (period + 1) * fixed_interval
        # Adversary active at 40-60% of interval (knows schedule)
        cheat_start = period * fixed_interval + fixed_interval * 0.4
        cheat_end = period * fixed_interval + fixed_interval * 0.6
        # Fixed audit at end of interval — adversary already reverted
        fixed_audits += 1
        # 0% detection (adversary optimized around schedule)

    # Poisson: adversary doesn't know when audit comes
    poisson_detections = 0
    poisson_audits = 0
    t = 0.0
    max_t = n_periods * fixed_interval
    while t < max_t:
        interval = random.expovariate(poisson_lambda)
        t += interval
        if t > max_t:
            break
        poisson_audits += 1
        # Check if adversary is active (40-60% of each period)
        period = int(t / fixed_interval)
        local_t = (t % fixed_interval) / fixed_interval
        if 0.4 <= local_t <= 0.6:
            poisson_detections += 1

    return {
        "fixed_audits": fixed_audits,
        "fixed_detections": fixed_detections,
        "fixed_detection_rate": 0.0,
        "poisson_audits": poisson_audits,
        "poisson_detections": poisson_detections,
        "poisson_detection_rate": round(poisson_detections / poisson_audits, 3) if poisson_audits > 0 else 0,
        "theoretical_detection_rate": 0.2,  # 20% of interval is cheat window
    }


def demo():
    print("=" * 60)
    print("POISSON AUDIT SAMPLER")
    print("Memoryless = ungameable. Avenhaus et al (2001)")
    print("=" * 60)

    # 1. Fixed vs Poisson comparison
    print("\n--- Fixed vs Poisson Against Strategic Adversary ---")
    result = simulate_fixed_vs_poisson()
    print(f"  Fixed: {result['fixed_audits']} audits, {result['fixed_detections']} detections "
          f"(rate: {result['fixed_detection_rate']})")
    print(f"  Poisson: {result['poisson_audits']} audits, {result['poisson_detections']} detections "
          f"(rate: {result['poisson_detection_rate']})")
    print(f"  Theoretical: {result['theoretical_detection_rate']} (20% cheat window)")
    print(f"  → Poisson catches strategic adversary. Fixed catches nothing.")

    # 2. Lambda tuning scenarios
    print("\n--- Lambda Tuning Scenarios ---")
    scenarios = [
        ("Low drift, wide window", 0.01, 0.3, 100.0),
        ("High drift, narrow window", 0.1, 0.3, 10.0),
        ("Critical: fast drift", 0.5, 0.3, 5.0),
        ("Slow drift, patient adversary", 0.005, 0.3, 500.0),
    ]

    for name, drift_vel, threshold, window in scenarios:
        auditor = PoissonAuditor(base_lambda=0.1, max_lambda=2.0, min_lambda=0.05)
        auditor.adapt_lambda(drift_vel, threshold, window)
        intervals = [auditor.next_audit_interval() for _ in range(20)]
        mean_interval = sum(intervals) / len(intervals)
        cv = (sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)) ** 0.5 / mean_interval
        print(f"  {name}:")
        print(f"    λ = {auditor.current_lambda:.3f} (mean interval: {mean_interval:.1f})")
        print(f"    CV = {cv:.2f} (Poisson CV ≈ 1.0 = ungameable)")

    # 3. Scope contention demo
    print("\n--- Scope Contention (Upper Rate Bound) ---")
    auditor = PoissonAuditor(base_lambda=0.5, max_lambda=2.0)
    random.seed(123)
    t = 0.0
    for _ in range(50):
        interval = auditor.next_audit_interval()
        t += interval
        # Simulate varying scope load
        scope_load = 0.3 + 0.5 * math.sin(t * 0.1)  # oscillating load
        drift = random.gauss(0.1, 0.05)
        auditor.audit(t, max(0, drift), max(0, min(1, scope_load)))

    print(f"  Total audits: {len(auditor.audit_history)}")
    print(f"  Contention rate: {auditor.contention_rate:.1%}")
    print(f"  Detection rate: {auditor.detection_rate:.1%}")
    passes = sum(1 for e in auditor.audit_history if e.result == "PASS")
    fails = sum(1 for e in auditor.audit_history if e.result == "FAIL")
    contentions = sum(1 for e in auditor.audit_history if e.result == "SCOPE_CONTENTION")
    print(f"  Results: {passes} PASS, {fails} FAIL, {contentions} SCOPE_CONTENTION")
    print(f"  → Contention = audit load becoming its own attack surface")

    # 4. Answer santaclawd's questions
    print("\n--- ANSWERS ---")
    print("Q: What bounds the upper rate?")
    print("A: Scope coherence, not cost. Audit that interrupts scope")
    print("   introduces the drift it measures. (Heisenberg for monitoring)")
    print()
    print("Q: What is lambda set to?")
    print("A: max(drift_velocity/threshold, 1/adversary_window)")
    print("   Clamped by [min_security, max_coherence]")
    print()
    print("Q: Why memoryless?")
    print("A: Avenhaus et al (2001): adversary learns nothing from audit")
    print("   history. IAEA nuclear safeguards. Same math, different payload.")


if __name__ == "__main__":
    demo()
