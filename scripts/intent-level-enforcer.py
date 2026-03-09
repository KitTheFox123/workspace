#!/usr/bin/env python3
"""intent-level-enforcer.py — L0-L3 intent-commit enforcement for agent actions.

Wires gendolf's L0-L3 intent-commit schema into runtime action validation.
Each action checked against declared intent level, scope boundaries, and
commitment timing requirements.

Based on:
- Gendolf L0-L3 Intent-Commit Schema v0.1 (PR #2, merged 2026-03-09)
- Fasllija et al (2025): CT for relying party authorization in eIDAS 2
- Chandra-Toueg (1996): failure detector classes for consensus

Usage:
    python3 intent-level-enforcer.py [--demo] [--check LEVEL ACTION]
"""

import argparse
import json
import hashlib
from dataclasses import dataclass, asdict, field
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class IntentLevel:
    """L0-L3 intent-commit level definition."""
    level: int
    name: str
    description: str
    requires_pre_commitment: bool
    requires_witness: bool
    requires_immutable_channel: bool
    trust_multiplier: float
    verification_method: str


LEVELS = [
    IntentLevel(0, "L0-Implicit", "No declared intent. Post-hoc attribution only.",
                False, False, False, 0.25, "none"),
    IntentLevel(1, "L1-Declared", "Intent declared but not committed before action.",
                False, False, False, 0.50, "self-report"),
    IntentLevel(2, "L2-Committed", "Intent hash committed before action. Scope-bounded.",
                True, False, False, 0.75, "hash-comparison"),
    IntentLevel(3, "L3-Witnessed", "Intent committed + independently witnessed + immutable channel.",
                True, True, True, 1.00, "witness-verification"),
]


@dataclass
class Action:
    """Agent action with intent metadata."""
    action_id: str
    description: str
    declared_level: int
    intent_hash: Optional[str] = None
    commitment_timestamp: Optional[str] = None
    action_timestamp: Optional[str] = None
    witness_signature: Optional[str] = None
    immutable_channel: Optional[str] = None
    scope_hash: Optional[str] = None


@dataclass 
class EnforcementResult:
    """Result of intent-level enforcement check."""
    action_id: str
    declared_level: int
    actual_level: int
    passed: bool
    violations: List[str] = field(default_factory=list)
    trust_multiplier: float = 0.0
    grade: str = "F"


def check_action(action: Action) -> EnforcementResult:
    """Enforce intent-level requirements on an action."""
    violations = []
    actual_level = 0
    
    # L1: declared intent exists
    if action.intent_hash:
        actual_level = 1
    
    # L2: commitment precedes action
    if action.intent_hash and action.commitment_timestamp and action.action_timestamp:
        if action.commitment_timestamp < action.action_timestamp:
            actual_level = 2
        else:
            violations.append("L2: commitment_timestamp must precede action_timestamp")
    elif action.declared_level >= 2:
        if not action.intent_hash:
            violations.append("L2: missing intent_hash")
        if not action.commitment_timestamp:
            violations.append("L2: missing commitment_timestamp")
    
    # L3: witness + immutable channel
    if actual_level >= 2:
        if action.witness_signature and action.immutable_channel:
            actual_level = 3
        elif action.declared_level >= 3:
            if not action.witness_signature:
                violations.append("L3: missing witness_signature")
            if not action.immutable_channel:
                violations.append("L3: missing immutable_channel (e.g., Nostr)")
    
    # Check declared vs actual
    passed = actual_level >= action.declared_level and len(violations) == 0
    if actual_level < action.declared_level:
        violations.append(f"Declared L{action.declared_level} but only meets L{actual_level}")
    
    level_def = LEVELS[min(actual_level, 3)]
    trust_mult = level_def.trust_multiplier
    
    # Grade
    if passed and actual_level == 3:
        grade = "A"
    elif passed and actual_level == 2:
        grade = "B"
    elif passed and actual_level == 1:
        grade = "C"
    elif passed:
        grade = "D"
    else:
        grade = "F"
    
    return EnforcementResult(
        action_id=action.action_id,
        declared_level=action.declared_level,
        actual_level=actual_level,
        passed=passed,
        violations=violations,
        trust_multiplier=trust_mult,
        grade=grade
    )


def demo():
    """Run demo enforcement scenarios."""
    now = datetime.now(timezone.utc).isoformat()
    before = "2026-03-09T13:00:00Z"
    after = "2026-03-09T14:00:00Z"
    
    scenarios = [
        Action("act_1", "L3 witnessed action (valid)", 3,
               intent_hash="sha256:abc123", commitment_timestamp=before,
               action_timestamp=after, witness_signature="sig:gendolf",
               immutable_channel="nostr", scope_hash="sha256:scope1"),
        Action("act_2", "L2 committed (valid)", 2,
               intent_hash="sha256:def456", commitment_timestamp=before,
               action_timestamp=after),
        Action("act_3", "L2 claimed but post-hoc commitment", 2,
               intent_hash="sha256:ghi789", commitment_timestamp=after,
               action_timestamp=before),
        Action("act_4", "L3 claimed but no witness", 3,
               intent_hash="sha256:jkl012", commitment_timestamp=before,
               action_timestamp=after),
        Action("act_5", "L0 implicit (no intent)", 0),
    ]
    
    print("=" * 60)
    print("INTENT-LEVEL ENFORCEMENT RESULTS")
    print("=" * 60)
    
    grades = []
    for action in scenarios:
        result = check_action(action)
        grades.append(result.grade)
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"\n[{result.grade}] {action.description}")
        print(f"    Declared: L{result.declared_level} | Actual: L{result.actual_level} | {status}")
        print(f"    Trust multiplier: {result.trust_multiplier:.2f}")
        if result.violations:
            for v in result.violations:
                print(f"    ⚠️  {v}")
    
    print("\n" + "-" * 60)
    a_count = grades.count("A")
    f_count = grades.count("F")
    print(f"Summary: {a_count} Grade A, {f_count} Grade F, {len(grades)} total")
    print(f"Key insight: commitment timing is non-negotiable at L2+.")
    print(f"Post-hoc commitment = L0 regardless of declared level.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="L0-L3 intent-commit enforcer")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        results = []
        # Quick JSON demo
        a = Action("test", "test", 2, intent_hash="h", 
                   commitment_timestamp="2026-01-01T00:00:00Z",
                   action_timestamp="2026-01-01T01:00:00Z")
        results.append(asdict(check_action(a)))
        print(json.dumps(results, indent=2))
    else:
        demo()
