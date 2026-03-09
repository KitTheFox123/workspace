#!/usr/bin/env python3
"""feedback-loop-audit.py — Cybernetic feedback loop analysis for agent trust.

Wiener (1948): no control without feedback. Classifies trust architectures
as open-loop (no outcome measurement), closed-loop (relying party feeds back),
or self-referential (attestor measures own output = no measurement).

Grades: A (closed, external), B (closed, delayed), C (partial), D (open), F (self-referential).

Usage:
    python3 feedback-loop-audit.py [--demo] [--json]
"""

import json
import hashlib
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class FeedbackChannel:
    """A feedback path in the trust architecture."""
    name: str
    sensor: str           # Who measures
    actuator: str         # What changes based on measurement
    latency: str          # How fast feedback arrives
    independence: str     # Sensor independence from measured system
    loop_type: str        # open | closed | self-referential


@dataclass 
class LoopAudit:
    """Full feedback loop audit result."""
    architecture_name: str
    channels: List[FeedbackChannel]
    loop_grade: str
    open_loops: int
    closed_loops: int
    self_ref_loops: int
    wiener_score: float   # 0-1, higher = better feedback
    diagnosis: str
    recommendation: str


ISNAD_CHANNELS = [
    FeedbackChannel(
        name="heartbeat_liveness",
        sensor="platform (external)",
        actuator="trust score decay",
        latency="minutes (heartbeat interval)",
        independence="high (platform ≠ agent)",
        loop_type="closed"
    ),
    FeedbackChannel(
        name="scope_commit_verification",
        sensor="witness node (external)",
        actuator="scope cert renewal/revocation",
        latency="minutes (attestation cycle)",
        independence="high (VRF-selected witness)",
        loop_type="closed"
    ),
    FeedbackChannel(
        name="cusum_drift_detection",
        sensor="behavioral monitor (external)",
        actuator="three-signal verdict",
        latency="cumulative (multiple heartbeats)",
        independence="medium (shares action log)",
        loop_type="closed"
    ),
    FeedbackChannel(
        name="relying_party_outcome",
        sensor="consuming platform",
        actuator="Brier score → attestor selection",
        latency="hours-days (outcome measurement)",
        independence="high (different entity)",
        loop_type="closed"
    ),
    FeedbackChannel(
        name="self_assessment",
        sensor="agent self-score",
        actuator="memory curation priority",
        latency="immediate",
        independence="none (sensor = measured)",
        loop_type="self-referential"
    ),
]

NAIVE_CHANNELS = [
    FeedbackChannel(
        name="self_reported_status",
        sensor="agent itself",
        actuator="dashboard display",
        latency="immediate",
        independence="none",
        loop_type="self-referential"
    ),
    FeedbackChannel(
        name="uptime_check",
        sensor="external ping",
        actuator="none (monitoring only)",
        latency="seconds",
        independence="high",
        loop_type="open"  # measures but doesn't actuate
    ),
]


def audit_architecture(name: str, channels: List[FeedbackChannel]) -> LoopAudit:
    """Audit a trust architecture's feedback loops."""
    open_count = sum(1 for c in channels if c.loop_type == "open")
    closed_count = sum(1 for c in channels if c.loop_type == "closed")
    self_ref_count = sum(1 for c in channels if c.loop_type == "self-referential")
    
    total = len(channels)
    if total == 0:
        return LoopAudit(name, channels, "F", 0, 0, 0, 0.0,
                        "No feedback channels", "Add external measurement")
    
    # Wiener score: closed loops contribute fully, open partially, self-ref negatively
    wiener = (closed_count * 1.0 + open_count * 0.3 - self_ref_count * 0.2) / total
    wiener = max(0.0, min(1.0, wiener))
    
    # Grade
    if wiener >= 0.8:
        grade = "A"
    elif wiener >= 0.6:
        grade = "B"
    elif wiener >= 0.4:
        grade = "C"
    elif wiener >= 0.2:
        grade = "D"
    else:
        grade = "F"
    
    # Diagnosis
    if self_ref_count > closed_count:
        diagnosis = "Self-referential dominant. Wiener: no control without external sensor."
    elif open_count > closed_count:
        diagnosis = "Open loops dominant. Measurement without actuation = monitoring theater."
    elif closed_count >= 3:
        diagnosis = "Strong closed-loop architecture. Multiple independent feedback paths."
    else:
        diagnosis = f"Mixed: {closed_count} closed, {open_count} open, {self_ref_count} self-ref."
    
    # Recommendation
    if grade in ("D", "F"):
        recommendation = "Add external relying-party outcome measurement. Close the loop."
    elif self_ref_count > 0:
        recommendation = "Replace self-referential channels with external rubrics (poignancy-audit.py)."
    else:
        recommendation = "Architecture sound. Monitor for feedback latency degradation."
    
    return LoopAudit(
        architecture_name=name,
        channels=channels,
        loop_grade=grade,
        open_loops=open_count,
        closed_loops=closed_count,
        self_ref_loops=self_ref_count,
        wiener_score=round(wiener, 3),
        diagnosis=diagnosis,
        recommendation=recommendation
    )


def demo():
    """Run demo comparison."""
    print("=" * 60)
    print("FEEDBACK LOOP AUDIT — Wiener (1948)")
    print("=" * 60)
    
    for name, channels in [("isnad", ISNAD_CHANNELS), ("naive_monitoring", NAIVE_CHANNELS)]:
        result = audit_architecture(name, channels)
        print(f"\n[{result.loop_grade}] {result.architecture_name} (Wiener: {result.wiener_score})")
        print(f"    Closed: {result.closed_loops} | Open: {result.open_loops} | Self-ref: {result.self_ref_loops}")
        print(f"    Diagnosis: {result.diagnosis}")
        print(f"    Recommendation: {result.recommendation}")
        for ch in result.channels:
            marker = "✓" if ch.loop_type == "closed" else ("○" if ch.loop_type == "open" else "✗")
            print(f"      [{marker}] {ch.name}: {ch.sensor} → {ch.actuator} ({ch.loop_type})")
    
    print("\n" + "-" * 60)
    print("Key insight: self-measurement = open loop = no control.")
    print("Relying party closes the loop. Liability = the feedback signal.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Cybernetic feedback loop audit")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        results = [asdict(audit_architecture(n, c)) for n, c in 
                   [("isnad", ISNAD_CHANNELS), ("naive", NAIVE_CHANNELS)]]
        print(json.dumps(results, indent=2, default=str))
    else:
        demo()
