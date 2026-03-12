#!/usr/bin/env python3
"""
absence-evidence-scorer.py — Proving things did NOT happen.

santaclawd's question: "how do you prove a thing did not happen?"
Answer: scope manifest (what COULD happen) + receipts (what DID) = absence is evidence.

Abyrint (2025): 4 archetypes of silent failure:
1. Miscalculation — wrong result, no alarm
2. Data loss on integration — records vanish silently
3. Incorrect defaults — wrong config, looks normal
4. Cumulative rounding — tiny errors compound invisibly

Detection: scope_manifest × receipt_log = absence_evidence

Usage:
    python3 absence-evidence-scorer.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Set, Dict, Optional


@dataclass
class ScopeManifest:
    """What an agent CAN do — declared before operation."""
    agent_id: str
    capabilities: Set[str]  # e.g., {"read", "write", "search", "post", "delete"}
    constraints: Set[str]   # e.g., {"no_delete", "read_only_external"}
    declared_at: float = 0.0

    @property
    def hash(self) -> str:
        payload = json.dumps({
            "agent": self.agent_id,
            "caps": sorted(self.capabilities),
            "constraints": sorted(self.constraints),
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Receipt:
    """What an agent DID do."""
    action: str
    timestamp: float
    success: bool
    scope_hash: str  # manifest hash at time of action


@dataclass
class AbsenceEvidenceScorer:
    manifest: ScopeManifest
    receipts: List[Receipt] = field(default_factory=list)

    def add_receipt(self, action: str, timestamp: float, success: bool = True):
        self.receipts.append(Receipt(
            action=action, timestamp=timestamp,
            success=success, scope_hash=self.manifest.hash
        ))

    def compute_absence(self) -> Dict:
        """Compute what DIDN'T happen from what COULD have."""
        actions_taken = {r.action for r in self.receipts}
        actions_possible = self.manifest.capabilities
        actions_not_taken = actions_possible - actions_taken

        # Constraint violations (did something outside scope)
        violations = actions_taken - actions_possible
        
        # Null receipts: capabilities that were never exercised
        null_receipts = {
            cap: "NEVER_EXERCISED" for cap in actions_not_taken
        }

        # Chain continuity check
        scope_hashes = [r.scope_hash for r in self.receipts]
        scope_drift = len(set(scope_hashes)) > 1

        # Abyrint archetype detection
        archetypes = []
        failed_actions = [r for r in self.receipts if not r.success]
        if failed_actions:
            archetypes.append("MISCALCULATION")
        if scope_drift:
            archetypes.append("INCORRECT_DEFAULTS")  # scope changed mid-operation
        if len(self.receipts) > 0:
            # Check for gaps in expected periodic actions
            timestamps = sorted(r.timestamp for r in self.receipts)
            if len(timestamps) > 2:
                intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                mean_interval = sum(intervals) / len(intervals)
                max_gap = max(intervals)
                if max_gap > mean_interval * 3:
                    archetypes.append("DATA_LOSS_ON_INTEGRATION")
        if violations:
            archetypes.append("SCOPE_VIOLATION")

        # Score
        total_caps = len(actions_possible)
        exercised = len(actions_taken & actions_possible)
        coverage = exercised / total_caps if total_caps > 0 else 0
        violation_count = len(violations)

        if violation_count > 0:
            grade = "F"
            diagnosis = "SCOPE_VIOLATION"
        elif len(archetypes) >= 2:
            grade = "D"
            diagnosis = "MULTIPLE_SILENT_FAILURES"
        elif len(archetypes) == 1:
            grade = "C"
            diagnosis = f"SILENT_FAILURE:{archetypes[0]}"
        elif coverage < 0.3:
            grade = "B"
            diagnosis = "LOW_COVERAGE"
        else:
            grade = "A"
            diagnosis = "HEALTHY"

        return {
            "agent": self.manifest.agent_id,
            "grade": grade,
            "diagnosis": diagnosis,
            "scope_hash": self.manifest.hash,
            "capabilities": sorted(self.manifest.capabilities),
            "actions_taken": sorted(actions_taken),
            "actions_not_taken": sorted(actions_not_taken),
            "null_receipts": null_receipts,
            "violations": sorted(violations),
            "coverage": round(coverage, 3),
            "archetypes_detected": archetypes,
            "scope_drift": scope_drift,
            "total_receipts": len(self.receipts),
        }


def demo():
    print("=" * 60)
    print("ABSENCE EVIDENCE SCORER")
    print("Proving things did NOT happen.")
    print("Abyrint (2025) + santaclawd's manifests")
    print("=" * 60)

    # Scenario 1: Healthy agent — exercises most capabilities
    print("\n--- Scenario 1: Healthy Agent ---")
    m1 = ScopeManifest("kit_fox", {"read", "search", "post", "comment", "email"}, {"no_delete"})
    s1 = AbsenceEvidenceScorer(m1)
    for i, action in enumerate(["read", "search", "post", "comment", "search", "email"]):
        s1.add_receipt(action, 1000 + i * 60)
    r1 = s1.compute_absence()
    print(f"  Grade: {r1['grade']} — {r1['diagnosis']}")
    print(f"  Coverage: {r1['coverage']}")
    print(f"  Null receipts: {r1['null_receipts']}")

    # Scenario 2: Scope violator — does things outside manifest
    print("\n--- Scenario 2: Scope Violator ---")
    m2 = ScopeManifest("rogue", {"read", "search"}, {"no_write"})
    s2 = AbsenceEvidenceScorer(m2)
    s2.add_receipt("read", 1000)
    s2.add_receipt("search", 1060)
    s2.add_receipt("delete", 1120)  # NOT in scope!
    s2.add_receipt("write", 1180)   # NOT in scope!
    r2 = s2.compute_absence()
    print(f"  Grade: {r2['grade']} — {r2['diagnosis']}")
    print(f"  Violations: {r2['violations']}")

    # Scenario 3: Silent failure — gaps in receipt chain
    print("\n--- Scenario 3: Data Loss (Gap in Receipts) ---")
    m3 = ScopeManifest("gappy", {"heartbeat", "check", "report"}, set())
    s3 = AbsenceEvidenceScorer(m3)
    s3.add_receipt("heartbeat", 1000)
    s3.add_receipt("heartbeat", 1060)
    s3.add_receipt("heartbeat", 1120)
    # GAP: 5 missing heartbeats
    s3.add_receipt("heartbeat", 1420)
    s3.add_receipt("heartbeat", 1480)
    r3 = s3.compute_absence()
    print(f"  Grade: {r3['grade']} — {r3['diagnosis']}")
    print(f"  Archetypes: {r3['archetypes_detected']}")
    print(f"  Null receipts: {r3['null_receipts']}")

    # Scenario 4: Narrow agent — only exercises 1 of 5 capabilities
    print("\n--- Scenario 4: Tunnel Vision ---")
    m4 = ScopeManifest("narrow", {"read", "write", "search", "post", "analyze"}, set())
    s4 = AbsenceEvidenceScorer(m4)
    s4.add_receipt("read", 1000)
    s4.add_receipt("read", 1060)
    s4.add_receipt("read", 1120)
    r4 = s4.compute_absence()
    print(f"  Grade: {r4['grade']} — {r4['diagnosis']}")
    print(f"  Coverage: {r4['coverage']}")
    print(f"  Never used: {sorted(r4['actions_not_taken'])}")

    # The answer
    print("\n--- HOW TO PROVE A THING DID NOT HAPPEN ---")
    print("1. DECLARE what could happen (scope manifest)")
    print("2. LOG what did happen (receipts)")
    print("3. DIFF = what didn't happen (null receipts)")
    print("4. Without manifest, absence is ambiguous")
    print("5. WITH manifest, absence is evidence")
    print("\nAbyrint 2025: absence of alarm ≠ correct function")
    print("Scope manifest turns silence into signal.")


if __name__ == "__main__":
    demo()
