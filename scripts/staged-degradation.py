#!/usr/bin/env python3
"""staged-degradation.py — ATC-inspired graceful degradation for agent trust.

Models 4-stage degradation (Normal → Warn → Degrade → Halt) based on
NASA ATC graceful degradation research (Edwards & Lee 2018). Binary
halt loses work; silent continuation loses trust. Staged degradation
preserves both.

Each stage has: allowed actions, notification requirements, escalation
conditions, and de-escalation paths.

Usage:
    python3 staged-degradation.py [--demo] [--evaluate SCORE]
"""

import argparse
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import List, Optional


class DegradationLevel(IntEnum):
    NORMAL = 0
    WARN = 1
    DEGRADE = 2
    HALT = 3


@dataclass
class DegradationStage:
    level: int
    name: str
    description: str
    allowed_actions: List[str]
    blocked_actions: List[str]
    notifications: List[str]
    escalation_condition: str
    deescalation_condition: str
    atc_parallel: str


STAGES = [
    DegradationStage(
        level=0,
        name="NORMAL",
        description="Full operational authority within scope",
        allowed_actions=["read", "write", "execute", "delegate", "communicate"],
        blocked_actions=[],
        notifications=["routine heartbeat log"],
        escalation_condition="Three-signal verdict detects anomaly (any signal failing)",
        deescalation_condition="N/A (already normal)",
        atc_parallel="Normal operations, full sector capacity"
    ),
    DegradationStage(
        level=1,
        name="WARN",
        description="Scope-constrained ops, no new authorizations, principal notified",
        allowed_actions=["read", "write", "execute_existing", "communicate"],
        blocked_actions=["delegate", "new_authorizations", "scope_expansion"],
        notifications=["principal alert", "action log frequency doubled"],
        escalation_condition="Warn persists > TTL/2 without principal acknowledgment",
        deescalation_condition="Principal acknowledges + anomaly resolves within TTL/2",
        atc_parallel="Reduced capacity, increased separation, supervisor notified"
    ),
    DegradationStage(
        level=2,
        name="DEGRADE",
        description="Read-only plus existing commitments, no new work",
        allowed_actions=["read", "complete_in_progress", "communicate_status"],
        blocked_actions=["write_new", "execute_new", "delegate", "external_actions"],
        notifications=["principal urgent alert", "continuous action logging"],
        escalation_condition="Degrade persists > TTL without principal re-signing scope",
        deescalation_condition="Principal re-signs scope cert with fresh TTL",
        atc_parallel="Manual backup mode, traffic management initiatives active"
    ),
    DegradationStage(
        level=3,
        name="HALT",
        description="No actions, signed halt attestation, await principal",
        allowed_actions=["emit_halt_attestation", "respond_to_principal_query"],
        blocked_actions=["all_autonomous_actions"],
        notifications=["halt attestation signed and published", "principal emergency alert"],
        escalation_condition="N/A (terminal state)",
        deescalation_condition="Principal issues new scope cert + reviews halt cause",
        atc_parallel="Sector closed, traffic rerouted to adjacent sectors"
    ),
]


@dataclass
class TrustSignals:
    """Three-signal verdict inputs."""
    liveness: bool  # Heartbeat active
    intent: bool    # Scope-commit matches actions
    drift: float    # CUSUM drift score (0.0 = no drift, 1.0 = max drift)


def evaluate_degradation(signals: TrustSignals, current_level: int = 0) -> dict:
    """Determine degradation level from three-signal verdict."""
    
    # Scoring
    issues = []
    if not signals.liveness:
        issues.append("liveness_failure")
    if not signals.intent:
        issues.append("intent_mismatch")
    if signals.drift > 0.7:
        issues.append("high_drift")
    elif signals.drift > 0.4:
        issues.append("moderate_drift")
    
    # Level determination
    if len(issues) == 0:
        target_level = DegradationLevel.NORMAL
        diagnosis = "All signals healthy"
    elif len(issues) == 1 and "moderate_drift" in issues:
        target_level = DegradationLevel.WARN
        diagnosis = f"Single moderate anomaly: {issues[0]}"
    elif len(issues) == 1:
        target_level = DegradationLevel.WARN if "high_drift" not in issues else DegradationLevel.DEGRADE
        diagnosis = f"Single failure: {issues[0]}"
    elif len(issues) == 2:
        target_level = DegradationLevel.DEGRADE
        diagnosis = f"Multiple failures: {', '.join(issues)}"
    else:
        target_level = DegradationLevel.HALT
        diagnosis = f"Critical: {', '.join(issues)}"
    
    # Never skip levels (gradual escalation)
    if target_level > current_level + 1:
        actual_level = current_level + 1
        note = f"Escalating one step (target={STAGES[target_level].name}, actual={STAGES[actual_level].name})"
    else:
        actual_level = target_level
        note = None
    
    stage = STAGES[actual_level]
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signals": {
            "liveness": signals.liveness,
            "intent": signals.intent,
            "drift": signals.drift,
        },
        "diagnosis": diagnosis,
        "issues": issues,
        "previous_level": STAGES[current_level].name,
        "target_level": STAGES[target_level].name,
        "actual_level": stage.name,
        "note": note,
        "stage": asdict(stage),
    }


def demo():
    """Run demo scenarios."""
    scenarios = [
        ("Healthy agent", TrustSignals(True, True, 0.1), 0),
        ("Slight drift", TrustSignals(True, True, 0.5), 0),
        ("High drift", TrustSignals(True, True, 0.8), 0),
        ("Liveness failure", TrustSignals(False, True, 0.2), 0),
        ("Intent mismatch + drift", TrustSignals(True, False, 0.6), 0),
        ("Everything failing", TrustSignals(False, False, 0.9), 0),
        ("Escalation from WARN", TrustSignals(False, False, 0.9), 1),
    ]
    
    print("=" * 60)
    print("STAGED DEGRADATION DEMO (ATC-inspired)")
    print("=" * 60)
    
    for name, signals, current in scenarios:
        result = evaluate_degradation(signals, current)
        print(f"\n--- {name} ---")
        print(f"  Signals: L={signals.liveness} I={signals.intent} D={signals.drift:.1f}")
        print(f"  From: {result['previous_level']} → {result['actual_level']}")
        print(f"  Diagnosis: {result['diagnosis']}")
        if result['note']:
            print(f"  Note: {result['note']}")
        print(f"  Allowed: {', '.join(result['stage']['allowed_actions'])}")
        print(f"  Blocked: {', '.join(result['stage']['blocked_actions'])}")
        print(f"  ATC parallel: {result['stage']['atc_parallel']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATC-inspired staged degradation")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps([asdict(s) for s in STAGES], indent=2))
    else:
        demo()
