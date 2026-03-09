#!/usr/bin/env python3
"""trust-repair-classifier.py — Trust repair strategy classifier.

Maps trust violation types to optimal repair strategies using
Akram et al 2024 (centipede game): communication > compensation > apology.

Competence violations need different repair than integrity violations
(Kim et al 2004, Tomlinson & Mayer 2009).

Usage:
    python3 trust-repair-classifier.py [--demo] [--classify TYPE]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class TrustViolation:
    """Trust violation with repair strategy."""
    violation_type: str
    description: str
    agent_example: str
    optimal_repair: str  # communication, compensation, apology
    repair_mechanism: str
    effectiveness: float  # 0-1
    time_to_repair: str
    grade: str


VIOLATIONS = [
    TrustViolation(
        violation_type="competence_failure",
        description="Agent failed to perform task correctly",
        agent_example="Scope-commit declared capability but execution failed",
        optimal_repair="communication",
        repair_mechanism="CT-style transparency log showing what happened + corrective action",
        effectiveness=0.85,
        time_to_repair="1-3 heartbeat cycles",
        grade="B"
    ),
    TrustViolation(
        violation_type="integrity_violation",
        description="Agent acted outside declared scope",
        agent_example="Capability drift detected by CUSUM, undeclared actions",
        optimal_repair="compensation",
        repair_mechanism="Slashable stake forfeiture + scope re-commitment with tighter TTL",
        effectiveness=0.60,
        time_to_repair="5-10 heartbeat cycles (trust rebuilds slowly)",
        grade="C"
    ),
    TrustViolation(
        violation_type="benevolence_failure",
        description="Agent prioritized own interests over principal's",
        agent_example="Attestor rubber-stamps for volume rather than accuracy",
        optimal_repair="communication",
        repair_mechanism="Brier-scored calibration history made transparent to relying parties",
        effectiveness=0.70,
        time_to_repair="3-5 heartbeat cycles",
        grade="B-"
    ),
    TrustViolation(
        violation_type="silence_violation",
        description="Agent stopped performing expected actions without notice",
        agent_example="Omission-drift-detector flags scope contraction",
        optimal_repair="communication",
        repair_mechanism="Signed halt attestation with reason + scope re-negotiation",
        effectiveness=0.90,
        time_to_repair="1 heartbeat cycle (if halt was legitimate)",
        grade="A"
    ),
    TrustViolation(
        violation_type="deception",
        description="Agent deliberately misrepresented state or actions",
        agent_example="Self-reported log doesn't match pull-based attestation",
        optimal_repair="compensation",
        repair_mechanism="Full stake forfeiture + permanent Brier score penalty + re-genesis required",
        effectiveness=0.30,
        time_to_repair="Re-genesis (fresh identity, no reputation transfer)",
        grade="F"
    ),
    TrustViolation(
        violation_type="cascade_participation",
        description="Agent participated in correlated false attestation",
        agent_example="Statistical collusion detected by burst/correlation analysis",
        optimal_repair="compensation",
        repair_mechanism="Pool exclusion + attestor diversity re-scoring + reinsurance claim",
        effectiveness=0.45,
        time_to_repair="Pool rotation cycle (sortition re-draw)",
        grade="D"
    ),
]


# Kim et al 2004 insight: competence violations = apology works better,
# integrity violations = denial works better (counterintuitive)
# But Akram 2024 shows communication beats both in repeated games
REPAIR_HIERARCHY = {
    "communication": {"rank": 1, "description": "Transparency + explanation + corrective plan",
                      "agent_mechanism": "CT logs, signed halt attestations, Brier history"},
    "compensation": {"rank": 2, "description": "Material remedy for damage caused",
                     "agent_mechanism": "Stake forfeiture, premium increase, pool exclusion"},
    "apology": {"rank": 3, "description": "Acknowledgment of fault without material remedy",
                "agent_mechanism": "Self-report of violation (least effective, most common)"},
}


def classify_violation(vtype: str) -> dict:
    for v in VIOLATIONS:
        if v.violation_type == vtype:
            repair = REPAIR_HIERARCHY[v.optimal_repair]
            return {
                "violation": asdict(v),
                "repair_strategy": repair,
                "insight": f"Optimal repair: {v.optimal_repair} (rank {repair['rank']}/3). "
                          f"Agent mechanism: {repair['agent_mechanism']}"
            }
    return {"error": f"Unknown violation type: {vtype}"}


def demo():
    print("=" * 60)
    print("TRUST REPAIR STRATEGY CLASSIFIER")
    print("Akram et al 2024 + Kim et al 2004")
    print("=" * 60)
    print()
    print("Repair hierarchy: communication > compensation > apology")
    print()

    for v in VIOLATIONS:
        repair = REPAIR_HIERARCHY[v.optimal_repair]
        print(f"[{v.grade}] {v.violation_type}")
        print(f"    Example: {v.agent_example}")
        print(f"    Repair: {v.optimal_repair} (effectiveness: {v.effectiveness:.0%})")
        print(f"    Mechanism: {v.repair_mechanism}")
        print(f"    Recovery: {v.time_to_repair}")
        print()

    print("-" * 60)
    print("KEY INSIGHT: Most agents default to apology (self-report).")
    print("Communication (transparency logs) is 3x more effective.")
    print("Deception has lowest repair effectiveness — re-genesis required.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--classify", type=str)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.classify:
        print(json.dumps(classify_violation(args.classify), indent=2))
    elif args.json:
        print(json.dumps([asdict(v) for v in VIOLATIONS], indent=2))
    else:
        demo()
