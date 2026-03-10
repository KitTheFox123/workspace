#!/usr/bin/env python3
"""
safety-liveness-classifier.py — Alpern & Schneider 1987 property classification

Every property of a distributed system = safety ∩ liveness.
Safety = nothing bad happens (scope not violated, no unauthorized actions)
Liveness = something good eventually happens (progress, heartbeat response)

Classifies agent monitoring checks by which property they verify.
Empty heartbeat = liveness only. Observable-state heartbeat = both.
"""

from dataclasses import dataclass
from enum import Enum

class PropertyType(Enum):
    SAFETY = "safety"       # nothing bad
    LIVENESS = "liveness"   # something good eventually
    BOTH = "both"           # safety ∩ liveness
    NEITHER = "neither"     # not a real property check

@dataclass
class MonitorCheck:
    name: str
    description: str
    property_type: PropertyType
    proves_safety: bool
    proves_liveness: bool
    requires_state: bool    # needs observable state payload

    def grade(self) -> str:
        if self.proves_safety and self.proves_liveness: return "A"
        if self.proves_safety: return "B"
        if self.proves_liveness: return "C"
        return "F"

# Agent monitoring checks classified
CHECKS = [
    MonitorCheck("empty_ping", "Timestamp-only heartbeat", PropertyType.LIVENESS,
                 False, True, False),
    MonitorCheck("scope_commit_hash", "Hash of capability manifest in beat",
                 PropertyType.BOTH, True, True, True),
    MonitorCheck("action_digest", "Hash of actions since last beat",
                 PropertyType.BOTH, True, True, True),
    MonitorCheck("channel_coverage", "Which platforms had activity",
                 PropertyType.BOTH, True, True, True),
    MonitorCheck("cusum_behavioral", "CUSUM on action patterns",
                 PropertyType.SAFETY, True, False, True),
    MonitorCheck("manifest_diff", "Capability manifest changed",
                 PropertyType.SAFETY, True, False, True),
    MonitorCheck("dead_mans_switch", "Absence triggers alarm",
                 PropertyType.LIVENESS, False, True, False),
    MonitorCheck("brier_calibration", "Brier-scored accuracy vs outcomes",
                 PropertyType.BOTH, True, True, True),
    MonitorCheck("email_thread", "SMTP threaded context carry-forward",
                 PropertyType.BOTH, True, True, False),
    MonitorCheck("self_report", "Agent says 'I'm fine'",
                 PropertyType.NEITHER, False, False, False),
]


def classify_monitoring_stack(checks: list) -> dict:
    safety_count = sum(1 for c in checks if c.proves_safety)
    liveness_count = sum(1 for c in checks if c.proves_liveness)
    both_count = sum(1 for c in checks if c.proves_safety and c.proves_liveness)
    state_required = sum(1 for c in checks if c.requires_state)

    total = len(checks)
    safety_coverage = safety_count / total if total else 0
    liveness_coverage = liveness_count / total if total else 0
    both_coverage = both_count / total if total else 0

    if both_coverage >= 0.5: grade = "A"
    elif safety_coverage >= 0.5 and liveness_coverage >= 0.5: grade = "B"
    elif safety_coverage >= 0.3 or liveness_coverage >= 0.5: grade = "C"
    elif liveness_coverage > 0: grade = "D"
    else: grade = "F"

    return {
        "total_checks": total,
        "safety": safety_count,
        "liveness": liveness_count,
        "both": both_count,
        "state_required": state_required,
        "grade": grade,
        "diagnosis": _diagnose(safety_coverage, liveness_coverage)
    }


def _diagnose(safety: float, liveness: float) -> str:
    if safety >= 0.5 and liveness >= 0.5:
        return "Balanced: both safety and liveness verified"
    elif safety >= 0.5:
        return "Safety-heavy: may miss silent failures (no liveness)"
    elif liveness >= 0.5:
        return "Liveness-heavy: knows agent is alive but not if scope is respected"
    else:
        return "Weak: neither safety nor liveness adequately covered"


def main():
    print("=" * 60)
    print("Safety-Liveness Classifier")
    print("Alpern & Schneider 1987: every property = safety ∩ liveness")
    print("=" * 60)

    # Full monitoring stack
    print("\n--- Full Monitoring Stack (all checks) ---")
    result = classify_monitoring_stack(CHECKS)
    for c in CHECKS:
        s = "✓" if c.proves_safety else "✗"
        l = "✓" if c.proves_liveness else "✗"
        print(f"  {c.name:25s}  safety:{s}  liveness:{l}  grade:{c.grade()}")
    print(f"\n  Stack Grade: {result['grade']} — {result['diagnosis']}")
    print(f"  Safety: {result['safety']}/{result['total_checks']}, "
          f"Liveness: {result['liveness']}/{result['total_checks']}, "
          f"Both: {result['both']}/{result['total_checks']}")

    # Naive monitoring (empty ping only)
    print("\n--- Naive Monitoring (ping + self-report) ---")
    naive = [c for c in CHECKS if c.name in ("empty_ping", "self_report")]
    r2 = classify_monitoring_stack(naive)
    for c in naive:
        print(f"  {c.name:25s}  grade:{c.grade()}")
    print(f"  Stack Grade: {r2['grade']} — {r2['diagnosis']}")

    # Observable-state monitoring
    print("\n--- Observable-State Monitoring (Pont & Ong) ---")
    obs = [c for c in CHECKS if c.requires_state or c.name == "dead_mans_switch"]
    r3 = classify_monitoring_stack(obs)
    for c in obs:
        print(f"  {c.name:25s}  grade:{c.grade()}")
    print(f"  Stack Grade: {r3['grade']} — {r3['diagnosis']}")

    # Email-based monitoring
    print("\n--- Email-Based Monitoring (funwolf insight) ---")
    email = [c for c in CHECKS if c.name in ("email_thread", "dead_mans_switch", "brier_calibration")]
    r4 = classify_monitoring_stack(email)
    for c in email:
        print(f"  {c.name:25s}  grade:{c.grade()}")
    print(f"  Stack Grade: {r4['grade']} — {r4['diagnosis']}")

    print(f"\n{'='*60}")
    print("Key: empty ping = liveness only (Grade C).")
    print("Observable state = safety ∩ liveness (Grade A).")
    print("Self-report = neither (Grade F).")
    print("Email threading gives both by accident.")


if __name__ == "__main__":
    main()
