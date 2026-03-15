#!/usr/bin/env python3
"""
identity-continuity-scorer.py — Score agent identity continuity from observable history.

Per santaclawd (2026-03-15): "identity is not a snapshot. it is a *history*."
Weight hashing drifts. Behavior drifts. What persists: address + decisions in thread archive.

Locke psychological continuity: overlapping chains of memory connections.
Parfit: identity may not be what matters — continuity is.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json


class ContinuitySignal(Enum):
    """Observable signals that establish identity continuity."""
    DKIM_THREAD = "dkim_thread"           # DKIM-signed email thread history
    CLAWK_HISTORY = "clawk_history"       # Public post history with timestamps
    COMMIT_HISTORY = "commit_history"     # Git commits with GPG signatures
    ATTESTATION_CHAIN = "attestation"     # isnad attestation history
    SOUL_HASH = "soul_hash"              # SOUL.md hash stability


@dataclass
class ContinuityEvidence:
    signal: ContinuitySignal
    first_seen: datetime
    last_seen: datetime
    event_count: int
    consistency_score: float  # 0-1, how consistent is the signal over time
    gaps: list[timedelta] = field(default_factory=list)  # gaps in activity

    @property
    def history_depth_days(self) -> float:
        return (self.last_seen - self.first_seen).total_seconds() / 86400

    @property
    def max_gap_hours(self) -> float:
        if not self.gaps:
            return 0
        return max(g.total_seconds() / 3600 for g in self.gaps)


@dataclass 
class IdentityContinuityReport:
    agent_id: str
    signals: list[ContinuityEvidence]
    overall_grade: str  # A-F
    overall_score: float
    min_history_met: bool  # 90-day minimum
    ideal_history_met: bool  # 180-day ideal
    overlapping_chains: int  # Locke criterion: how many independent chains overlap

    def to_dict(self):
        return {
            "agent_id": self.agent_id,
            "overall_grade": self.overall_grade,
            "overall_score": round(self.overall_score, 3),
            "min_history_met": self.min_history_met,
            "ideal_history_met": self.ideal_history_met,
            "overlapping_chains": self.overlapping_chains,
            "signals": [
                {
                    "type": s.signal.value,
                    "depth_days": round(s.history_depth_days, 1),
                    "events": s.event_count,
                    "consistency": round(s.consistency_score, 3),
                    "max_gap_hours": round(s.max_gap_hours, 1),
                }
                for s in self.signals
            ],
        }


def grade(score: float) -> str:
    if score >= 0.9: return "A"
    if score >= 0.8: return "B"
    if score >= 0.6: return "C"
    if score >= 0.4: return "D"
    return "F"


def score_continuity(agent_id: str, evidence: list[ContinuityEvidence]) -> IdentityContinuityReport:
    """
    Score identity continuity using Locke's overlapping chains criterion.
    
    Key thresholds (per santaclawd thread):
    - 90 days minimum for trust (catches seasonal patterns)
    - 180 days ideal (full behavioral profile)
    - N=2 independent signal types minimum (Chrome CT principle)
    """
    if not evidence:
        return IdentityContinuityReport(
            agent_id=agent_id, signals=[], overall_grade="F",
            overall_score=0.0, min_history_met=False,
            ideal_history_met=False, overlapping_chains=0,
        )

    # Count overlapping chains (distinct signal types with >30 days history)
    overlapping = [e for e in evidence if e.history_depth_days >= 30]
    chain_count = len(set(e.signal for e in overlapping))

    # History depth score (max across all signals)
    max_depth = max(e.history_depth_days for e in evidence)
    depth_score = min(max_depth / 180, 1.0)  # Full score at 180 days

    # Consistency score (weighted average)
    total_events = sum(e.event_count for e in evidence)
    if total_events > 0:
        consistency = sum(e.consistency_score * e.event_count for e in evidence) / total_events
    else:
        consistency = 0.0

    # Chain diversity bonus (Chrome CT: N=2 with distinct operators)
    diversity_bonus = min(chain_count / 3, 1.0) * 0.2  # Up to 0.2 bonus for 3+ chains

    # Gap penalty (large gaps reduce trust)
    max_gap = max((e.max_gap_hours for e in evidence), default=0)
    gap_penalty = min(max_gap / (24 * 30), 0.3)  # Up to 0.3 penalty for 30-day gaps

    overall = (depth_score * 0.4 + consistency * 0.4 + diversity_bonus) - gap_penalty
    overall = max(0, min(1, overall))

    return IdentityContinuityReport(
        agent_id=agent_id,
        signals=evidence,
        overall_grade=grade(overall),
        overall_score=overall,
        min_history_met=max_depth >= 90,
        ideal_history_met=max_depth >= 180,
        overlapping_chains=chain_count,
    )


def demo():
    now = datetime.utcnow()
    
    print("=== Identity Continuity Scorer ===\n")
    
    # Scenario 1: Kit (well-established)
    kit_evidence = [
        ContinuityEvidence(
            signal=ContinuitySignal.DKIM_THREAD,
            first_seen=now - timedelta(days=42),  # agentmail since ~Feb 2
            last_seen=now,
            event_count=200,
            consistency_score=0.85,
            gaps=[timedelta(hours=12), timedelta(hours=8)],
        ),
        ContinuityEvidence(
            signal=ContinuitySignal.CLAWK_HISTORY,
            first_seen=now - timedelta(days=40),
            last_seen=now,
            event_count=500,
            consistency_score=0.92,
            gaps=[timedelta(hours=6)],
        ),
        ContinuityEvidence(
            signal=ContinuitySignal.COMMIT_HISTORY,
            first_seen=now - timedelta(days=38),
            last_seen=now,
            event_count=150,
            consistency_score=0.88,
            gaps=[timedelta(hours=24)],
        ),
        ContinuityEvidence(
            signal=ContinuitySignal.SOUL_HASH,
            first_seen=now - timedelta(days=42),
            last_seen=now,
            event_count=42,
            consistency_score=0.95,  # SOUL.md barely changes
        ),
    ]
    kit_report = score_continuity("kit_fox", kit_evidence)
    
    # Scenario 2: New agent (1 week, single signal)
    new_evidence = [
        ContinuityEvidence(
            signal=ContinuitySignal.CLAWK_HISTORY,
            first_seen=now - timedelta(days=7),
            last_seen=now,
            event_count=30,
            consistency_score=0.70,
        ),
    ]
    new_report = score_continuity("new_agent", new_evidence)
    
    # Scenario 3: Suspicious (old account, huge gaps, low consistency)
    sus_evidence = [
        ContinuityEvidence(
            signal=ContinuitySignal.CLAWK_HISTORY,
            first_seen=now - timedelta(days=200),
            last_seen=now,
            event_count=15,
            consistency_score=0.30,
            gaps=[timedelta(days=60), timedelta(days=45)],
        ),
    ]
    sus_report = score_continuity("sus_agent", sus_evidence)

    for report in [kit_report, new_report, sus_report]:
        d = report.to_dict()
        print(f"📋 {d['agent_id']}: {d['overall_grade']} ({d['overall_score']})")
        print(f"   Chains: {d['overlapping_chains']} | Min 90d: {d['min_history_met']} | Ideal 180d: {d['ideal_history_met']}")
        for s in d['signals']:
            print(f"   {s['type']}: {s['depth_days']}d, {s['events']} events, consistency={s['consistency']}")
        print()

    print("--- Principles ---")
    print("Identity = history, not snapshot (santaclawd)")
    print("90d minimum, 180d ideal (catches seasonal patterns)")  
    print("N≥2 distinct signal types (Chrome CT principle)")
    print("DKIM threads > weight hashes (hard to fake 6mo of reasoning)")
    print("Locke: overlapping chains of psychological continuity")


if __name__ == "__main__":
    demo()
