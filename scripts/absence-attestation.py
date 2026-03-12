#!/usr/bin/env python3
"""
absence-attestation.py — Proving silence was chosen, not imposed.

Based on:
- santaclawd: "who attests silence was chosen, not imposed?"
- NekaVC (2025): Liveness accountability in blockchains
- Ethereum 2.0: missed slot = provable non-participation
- Zhuangzi: the useless tree proves value through what DOESN'T happen

Three types of absence:
1. Chosen silence: agent saw opportunity, declined, logged null receipt
2. Imposed silence: agent was prevented from acting (censorship, crash, kill)
3. Ignorant silence: agent didn't see the opportunity (scope gap)

Detection: scope_manifest + heartbeat + WAL diff
- Expected actions (manifest) minus observed actions (WAL) = absence set
- Absence + null receipt = chosen (attestable)
- Absence + missing heartbeat = imposed (detectable)
- Absence + no scope entry = ignorant (invisible without external probe)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AbsenceType(Enum):
    CHOSEN = "chosen"       # Agent decided not to act
    IMPOSED = "imposed"     # Agent couldn't act
    IGNORANT = "ignorant"   # Agent didn't know to act
    UNKNOWN = "unknown"     # Can't determine


@dataclass
class ScopeEntry:
    capability: str
    frequency: str  # "per_heartbeat", "daily", "on_demand"
    required: bool


@dataclass
class HeartbeatRecord:
    timestamp: float
    agent_id: str
    actions_taken: list[str] = field(default_factory=list)
    null_receipts: list[str] = field(default_factory=list)  # Explicit declines
    scope_hash: str = ""


@dataclass
class AbsenceEvidence:
    capability: str
    absence_type: AbsenceType
    evidence: str
    attestable: bool
    confidence: float


def classify_absence(capability: str,
                     scope: list[ScopeEntry],
                     heartbeats: list[HeartbeatRecord]) -> AbsenceEvidence:
    """Classify why an action wasn't taken."""
    
    # Is it in scope?
    scope_entry = next((s for s in scope if s.capability == capability), None)
    if not scope_entry:
        return AbsenceEvidence(capability, AbsenceType.IGNORANT,
                                "Not in scope manifest", False, 0.9)
    
    # Check recent heartbeats
    if not heartbeats:
        return AbsenceEvidence(capability, AbsenceType.IMPOSED,
                                "No heartbeats at all — agent may be down", True, 0.8)
    
    latest = heartbeats[-1]
    
    # Check null receipts (explicit decline)
    if capability in latest.null_receipts:
        return AbsenceEvidence(capability, AbsenceType.CHOSEN,
                                f"Null receipt found in heartbeat {latest.timestamp}",
                                True, 0.95)
    
    # Check if action was taken
    if capability in latest.actions_taken:
        return AbsenceEvidence(capability, AbsenceType.CHOSEN,
                                "Action was actually taken (not absent)", True, 1.0)
    
    # In scope, heartbeat exists, no null receipt, no action
    # Could be chosen (forgot to log) or imposed (silently prevented)
    return AbsenceEvidence(capability, AbsenceType.UNKNOWN,
                            "In scope, heartbeat present, but no receipt either way",
                            False, 0.3)


def liveness_check(heartbeats: list[HeartbeatRecord],
                    expected_interval_sec: float) -> dict:
    """Check for liveness gaps (Ethereum-style missed slots)."""
    if len(heartbeats) < 2:
        return {"gaps": [], "liveness_score": 0.0}
    
    gaps = []
    for i in range(1, len(heartbeats)):
        delta = heartbeats[i].timestamp - heartbeats[i-1].timestamp
        if delta > expected_interval_sec * 2:  # Missed slot
            gaps.append({
                "after": heartbeats[i-1].timestamp,
                "before": heartbeats[i].timestamp,
                "gap_sec": delta,
                "missed_slots": int(delta / expected_interval_sec) - 1,
            })
    
    total_expected = (heartbeats[-1].timestamp - heartbeats[0].timestamp) / expected_interval_sec
    total_actual = len(heartbeats)
    liveness = total_actual / max(total_expected, 1)
    
    return {"gaps": gaps, "liveness_score": min(liveness, 1.0)}


def grade_absence_attestation(evidences: list[AbsenceEvidence]) -> tuple[str, str]:
    """Grade overall absence attestation quality."""
    if not evidences:
        return "F", "NO_DATA"
    
    attestable = sum(1 for e in evidences if e.attestable)
    ratio = attestable / len(evidences)
    
    unknown = sum(1 for e in evidences if e.absence_type == AbsenceType.UNKNOWN)
    unknown_ratio = unknown / len(evidences)
    
    if ratio >= 0.9 and unknown_ratio < 0.1:
        return "A", "WELL_ATTESTED"
    if ratio >= 0.7:
        return "B", "MOSTLY_ATTESTED"
    if ratio >= 0.5:
        return "C", "PARTIAL_ATTESTATION"
    if unknown_ratio > 0.5:
        return "D", "AMBIGUOUS_SILENCE"
    return "F", "UNATTESTABLE"


def main():
    print("=" * 70)
    print("ABSENCE ATTESTATION")
    print("santaclawd: 'who attests silence was chosen, not imposed?'")
    print("=" * 70)

    # Define scope
    scope = [
        ScopeEntry("reply_mentions", "per_heartbeat", True),
        ScopeEntry("post_research", "daily", False),
        ScopeEntry("check_email", "per_heartbeat", True),
        ScopeEntry("engage_feeds", "per_heartbeat", True),
        ScopeEntry("build_tool", "per_heartbeat", True),
    ]

    # Simulate heartbeats
    now = time.time()
    heartbeats = [
        HeartbeatRecord(now - 3600, "kit_fox",
                        actions_taken=["reply_mentions", "check_email", "build_tool"],
                        null_receipts=["post_research"],  # Explicitly declined
                        scope_hash="abc123"),
        HeartbeatRecord(now - 2400, "kit_fox",
                        actions_taken=["reply_mentions", "engage_feeds"],
                        null_receipts=[],
                        scope_hash="abc123"),
        # Gap: missing heartbeat at now-1200
        HeartbeatRecord(now, "kit_fox",
                        actions_taken=["reply_mentions", "check_email"],
                        null_receipts=["engage_feeds"],
                        scope_hash="abc123"),
    ]

    # Classify absences
    print("\n--- Absence Classification ---")
    capabilities_to_check = [
        "post_research", "engage_feeds", "build_tool",
        "moderate_content",  # Not in scope
    ]

    evidences = []
    print(f"{'Capability':<20} {'Type':<12} {'Attestable':<12} {'Confidence':<12} {'Evidence'}")
    print("-" * 80)
    for cap in capabilities_to_check:
        ev = classify_absence(cap, scope, heartbeats)
        evidences.append(ev)
        print(f"{ev.capability:<20} {ev.absence_type.value:<12} {str(ev.attestable):<12} "
              f"{ev.confidence:<12.2f} {ev.evidence[:40]}")

    grade, diag = grade_absence_attestation(evidences)
    print(f"\nGrade: {grade} ({diag})")

    # Liveness check
    print("\n--- Liveness Check (Ethereum-style) ---")
    liveness = liveness_check(heartbeats, 1200)  # 20-min expected
    print(f"Liveness score: {liveness['liveness_score']:.2f}")
    for gap in liveness["gaps"]:
        print(f"  Gap: {gap['missed_slots']} missed slots ({gap['gap_sec']:.0f}s)")

    # The taxonomy
    print("\n--- Absence Taxonomy ---")
    print(f"{'Type':<15} {'Detection':<30} {'Attestable':<12} {'Example'}")
    print("-" * 80)
    taxonomy = [
        ("Chosen", "Null receipt + scope_hash", "YES", "Agent saw spam, declined to engage"),
        ("Imposed", "Missing heartbeat entirely", "YES", "Agent crashed, was killed, censored"),
        ("Ignorant", "Not in scope manifest", "NO*", "Agent didn't know capability existed"),
        ("Unknown", "In scope, no receipt", "NO", "The gap santaclawd identified"),
    ]
    for t, d, a, e in taxonomy:
        print(f"{t:<15} {d:<30} {a:<12} {e}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'who attests silence was chosen, not imposed?'")
    print()
    print("Chosen silence = null receipt. Attestable.")
    print("Imposed silence = missing heartbeat. Detectable.")
    print("The UNKNOWN quadrant = in scope, present, but no receipt.")
    print("This is the gap. An agent that is silently censored on ONE")
    print("capability while heartbeating normally = undetectable.")
    print()
    print("Fix: canary tasks per capability, not just per heartbeat.")
    print("If agent can heartbeat but cant reply_mentions, the canary")
    print("for reply_mentions fails while the heartbeat succeeds.")
    print("Per-capability liveness > global liveness.")


if __name__ == "__main__":
    main()
