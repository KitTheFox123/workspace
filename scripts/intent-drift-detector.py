#!/usr/bin/env python3
"""
intent-drift-detector.py — Detect objective drift in ATF receipt chains.

Per Moltbook "Compliance passed, objective drift won" post:
Compliance checks pass while the underlying objective silently changes.

Solution: hash the objective INTO each receipt. When the objective changes
but receipts still reference the old hash, drift is detected structurally.

Per Rasmussen (1997): systems drift toward the boundary of acceptable
performance. Per Goodhart: when the measure becomes the target, it ceases
to be a good measure. This tool catches both.

Three detection modes:
1. HASH_MISMATCH — objective_hash in receipt ≠ current objective_hash
2. STALE_INTENT — objective unchanged for > threshold despite changed context
3. SILENT_DRIFT — gradual shift in receipt content diverging from stated intent
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Objective:
    """A stated intent/goal that receipts are graded against."""
    objective_id: str
    description: str
    created_at: float
    hash: str = ""
    version: int = 1
    
    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(
                f"{self.objective_id}:{self.description}:{self.version}".encode()
            ).hexdigest()[:16]


@dataclass 
class Receipt:
    receipt_id: str
    agent_id: str
    timestamp: float
    evidence_grade: str
    objective_hash: str  # Hash of the objective this receipt was graded against
    content_keywords: list = field(default_factory=list)


@dataclass
class DriftEvent:
    event_type: str  # HASH_MISMATCH, STALE_INTENT, SILENT_DRIFT
    severity: str    # WARNING, CRITICAL
    receipt_id: str
    detail: str
    timestamp: float


# Thresholds (SPEC_CONSTANTS)
STALE_INTENT_DAYS = 14       # Objective unchanged for 14+ days = warning
STALE_INTENT_CRITICAL = 30   # 30+ days = critical
KEYWORD_DRIFT_THRESHOLD = 0.5  # Jaccard similarity < 0.5 = drift
MIN_RECEIPTS_FOR_DRIFT = 5   # Need 5+ receipts to detect silent drift


def detect_hash_mismatch(receipt: Receipt, current_objective: Objective) -> Optional[DriftEvent]:
    """Detect when receipt references outdated objective."""
    if receipt.objective_hash != current_objective.hash:
        return DriftEvent(
            event_type="HASH_MISMATCH",
            severity="CRITICAL",
            receipt_id=receipt.receipt_id,
            detail=f"Receipt references objective {receipt.objective_hash}, "
                   f"current is {current_objective.hash} (v{current_objective.version})",
            timestamp=receipt.timestamp
        )
    return None


def detect_stale_intent(objective: Objective, now: float) -> Optional[DriftEvent]:
    """Detect when objective hasn't been refreshed despite time passing."""
    age_days = (now - objective.created_at) / 86400
    if age_days > STALE_INTENT_CRITICAL:
        return DriftEvent(
            event_type="STALE_INTENT",
            severity="CRITICAL",
            receipt_id="N/A",
            detail=f"Objective v{objective.version} unchanged for {age_days:.0f} days "
                   f"(threshold: {STALE_INTENT_CRITICAL}d). Intent refresh required.",
            timestamp=now
        )
    elif age_days > STALE_INTENT_DAYS:
        return DriftEvent(
            event_type="STALE_INTENT",
            severity="WARNING",
            receipt_id="N/A",
            detail=f"Objective v{objective.version} unchanged for {age_days:.0f} days "
                   f"(threshold: {STALE_INTENT_DAYS}d). Consider intent refresh.",
            timestamp=now
        )
    return None


def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard similarity between two keyword sets."""
    if not set_a and not set_b:
        return 1.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def detect_silent_drift(receipts: list[Receipt], objective: Objective) -> list[DriftEvent]:
    """
    Detect gradual keyword drift in receipts away from stated intent.
    
    Even when objective_hash matches, the CONTENT of receipts may drift
    from the objective's semantic space. This catches Goodhart's Law:
    agents optimizing for the metric while the underlying work diverges.
    """
    events = []
    if len(receipts) < MIN_RECEIPTS_FOR_DRIFT:
        return events
    
    # Extract objective keywords from description
    obj_keywords = set(objective.description.lower().split())
    
    # Check drift in sliding windows
    window_size = max(3, len(receipts) // 3)
    
    # Early window
    early_keywords = set()
    for r in receipts[:window_size]:
        early_keywords.update(r.content_keywords)
    
    # Late window
    late_keywords = set()
    for r in receipts[-window_size:]:
        late_keywords.update(r.content_keywords)
    
    early_sim = jaccard_similarity(obj_keywords, early_keywords)
    late_sim = jaccard_similarity(obj_keywords, late_keywords)
    
    drift_magnitude = early_sim - late_sim
    
    if late_sim < KEYWORD_DRIFT_THRESHOLD and drift_magnitude > 0.15:
        events.append(DriftEvent(
            event_type="SILENT_DRIFT",
            severity="CRITICAL" if drift_magnitude > 0.3 else "WARNING",
            receipt_id=receipts[-1].receipt_id,
            detail=f"Content drift detected: early similarity={early_sim:.2f}, "
                   f"late similarity={late_sim:.2f}, drift={drift_magnitude:.2f}. "
                   f"Receipts diverging from stated objective.",
            timestamp=receipts[-1].timestamp
        ))
    
    return events


def audit_chain(receipts: list[Receipt], objective: Objective) -> dict:
    """Full drift audit on a receipt chain."""
    now = time.time()
    events = []
    
    # Check stale intent
    stale = detect_stale_intent(objective, now)
    if stale:
        events.append(stale)
    
    # Check each receipt for hash mismatch
    mismatches = 0
    for r in receipts:
        mismatch = detect_hash_mismatch(r, objective)
        if mismatch:
            events.append(mismatch)
            mismatches += 1
    
    # Check silent drift
    drift_events = detect_silent_drift(receipts, objective)
    events.extend(drift_events)
    
    # Grade
    critical = sum(1 for e in events if e.severity == "CRITICAL")
    warnings = sum(1 for e in events if e.severity == "WARNING")
    
    if critical > 0:
        grade = "F"
    elif warnings > 2:
        grade = "D"
    elif warnings > 0:
        grade = "C"
    elif mismatches == 0 and not drift_events:
        grade = "A"
    else:
        grade = "B"
    
    return {
        "objective_id": objective.objective_id,
        "objective_version": objective.version,
        "total_receipts": len(receipts),
        "hash_mismatches": mismatches,
        "drift_events": len(drift_events),
        "grade": grade,
        "events": [{"type": e.event_type, "severity": e.severity, "detail": e.detail} 
                   for e in events]
    }


# === Scenarios ===

def scenario_clean():
    """All receipts match current objective."""
    print("=== Scenario: Clean Chain ===")
    now = time.time()
    obj = Objective("obj1", "verify agent trust scores via counterparty receipts", now - 86400*5)
    receipts = [
        Receipt(f"r{i}", "kit_fox", now - 86400*(5-i), "A", obj.hash,
                ["verify", "trust", "counterparty", "receipts"])
        for i in range(8)
    ]
    result = audit_chain(receipts, obj)
    print(f"  Grade: {result['grade']}, Mismatches: {result['hash_mismatches']}, "
          f"Drift: {result['drift_events']}")
    print()


def scenario_objective_changed():
    """Objective updated but old receipts still reference old hash."""
    print("=== Scenario: Objective Changed (Hash Mismatch) ===")
    now = time.time()
    old_obj = Objective("obj1", "verify agent trust scores", now - 86400*20, version=1)
    new_obj = Objective("obj1", "verify agent trust AND delegation chains", now - 86400*2, version=2)
    
    receipts = [
        Receipt(f"r{i}", "kit_fox", now - 86400*(10-i), "B", old_obj.hash,
                ["verify", "trust", "scores"])
        for i in range(5)
    ] + [
        Receipt(f"r{i+5}", "kit_fox", now - 86400*(2-i%2), "A", new_obj.hash,
                ["verify", "trust", "delegation", "chains"])
        for i in range(3)
    ]
    
    result = audit_chain(receipts, new_obj)
    print(f"  Grade: {result['grade']}, Mismatches: {result['hash_mismatches']}")
    for e in result['events'][:3]:
        print(f"  [{e['severity']}] {e['type']}: {e['detail'][:80]}")
    print()


def scenario_stale_intent():
    """Objective not refreshed for 35 days."""
    print("=== Scenario: Stale Intent (No Refresh) ===")
    now = time.time()
    obj = Objective("obj1", "monitor agent compliance", now - 86400*35)
    receipts = [
        Receipt(f"r{i}", "kit_fox", now - 86400*i, "B", obj.hash,
                ["monitor", "compliance"])
        for i in range(10)
    ]
    result = audit_chain(receipts, obj)
    print(f"  Grade: {result['grade']}")
    for e in result['events']:
        print(f"  [{e['severity']}] {e['type']}: {e['detail'][:80]}")
    print()


def scenario_silent_drift():
    """Receipts gradually diverge from stated objective."""
    print("=== Scenario: Silent Drift (Goodhart's Law) ===")
    now = time.time()
    obj = Objective("obj1", "research security vulnerabilities in agent systems", now - 86400*3)
    
    # Early receipts match objective
    early = [
        Receipt(f"r{i}", "kit_fox", now - 86400*(10-i), "A", obj.hash,
                ["security", "vulnerabilities", "agent", "systems", "research"])
        for i in range(5)
    ]
    # Late receipts drift to engagement metrics
    late = [
        Receipt(f"r{i+5}", "kit_fox", now - 86400*(3-i%3), "A", obj.hash,
                ["engagement", "followers", "likes", "posts", "metrics"])
        for i in range(5)
    ]
    
    result = audit_chain(early + late, obj)
    print(f"  Grade: {result['grade']}, Drift events: {result['drift_events']}")
    for e in result['events']:
        print(f"  [{e['severity']}] {e['type']}: {e['detail'][:100]}")
    print()


if __name__ == "__main__":
    print("Intent Drift Detector — Objective Binding for ATF Receipts")
    print("Per Rasmussen (1997) + Goodhart's Law")
    print("=" * 65)
    print()
    scenario_clean()
    scenario_objective_changed()
    scenario_stale_intent()
    scenario_silent_drift()
    
    print("=" * 65)
    print("KEY INSIGHT: Compliance without intent binding is theater.")
    print("Hash the objective INTO the receipt. Mismatch = drift detected.")
    print("Three modes: HASH_MISMATCH, STALE_INTENT, SILENT_DRIFT.")
    print("Goodhart caught by keyword divergence even when hashes match.")
