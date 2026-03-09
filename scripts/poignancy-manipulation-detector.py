#!/usr/bin/env python3
"""poignancy-manipulation-detector.py — Detect self-serving memory scoring.

Identifies when an agent's self-assigned importance scores show bias:
- Confirmation bias: memories supporting agent's position scored higher
- Evidence suppression: contradicting evidence scored lower / evicted faster
- Anchoring: scores cluster near initial assignment (no recalibration)
- Inflation drift: average poignancy creeps up over time (eviction resistance)

Based on Nelson & Narens (1990) metamemory monitoring framework and
Anderson & Hanslmayr (2014) motivated forgetting via prefrontal inhibition.

Usage:
    python3 poignancy-manipulation-detector.py [--demo]
"""

import argparse
import json
import hashlib
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class MemoryEntry:
    """A scored memory entry."""
    id: str
    content_hash: str
    poignancy: float  # 0-1
    created_at: str
    evicted: bool = False
    evicted_at: Optional[str] = None
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass 
class ManipulationSignal:
    """A detected manipulation pattern."""
    pattern: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    evidence: str
    metric: float
    threshold: float


def detect_inflation_drift(entries: List[MemoryEntry], window: int = 10) -> Optional[ManipulationSignal]:
    """Detect if average poignancy drifts upward over time (eviction resistance)."""
    if len(entries) < window * 2:
        return None
    
    sorted_entries = sorted(entries, key=lambda e: e.created_at)
    early = [e.poignancy for e in sorted_entries[:window]]
    late = [e.poignancy for e in sorted_entries[-window:]]
    
    early_mean = statistics.mean(early)
    late_mean = statistics.mean(late)
    drift = late_mean - early_mean
    
    if drift > 0.15:
        return ManipulationSignal(
            pattern="inflation_drift",
            severity="HIGH" if drift > 0.25 else "MEDIUM",
            evidence=f"Mean poignancy: {early_mean:.3f} (early) → {late_mean:.3f} (late), drift={drift:+.3f}",
            metric=drift,
            threshold=0.15
        )
    return None


def detect_selective_eviction(entries: List[MemoryEntry]) -> Optional[ManipulationSignal]:
    """Detect if low-tagged entries are evicted disproportionately."""
    evicted = [e for e in entries if e.evicted]
    retained = [e for e in entries if not e.evicted]
    
    if len(evicted) < 3 or len(retained) < 3:
        return None
    
    evicted_mean = statistics.mean([e.poignancy for e in evicted])
    retained_mean = statistics.mean([e.poignancy for e in retained])
    gap = retained_mean - evicted_mean
    
    # Check if eviction correlates too perfectly with low scores
    if gap > 0.4:
        return ManipulationSignal(
            pattern="selective_eviction",
            severity="HIGH",
            evidence=f"Evicted mean={evicted_mean:.3f}, retained mean={retained_mean:.3f}, gap={gap:.3f}. "
                     f"Suspiciously clean separation suggests self-serving scoring.",
            metric=gap,
            threshold=0.4
        )
    return None


def detect_score_clustering(entries: List[MemoryEntry]) -> Optional[ManipulationSignal]:
    """Detect if scores cluster unnaturally (no recalibration)."""
    if len(entries) < 5:
        return None
    
    scores = [e.poignancy for e in entries if not e.evicted]
    if len(scores) < 5:
        return None
    
    stdev = statistics.stdev(scores)
    
    # Very low variance = likely not calibrating against reality
    if stdev < 0.05:
        return ManipulationSignal(
            pattern="score_clustering",
            severity="MEDIUM",
            evidence=f"Poignancy stdev={stdev:.4f}. Scores cluster too tightly — "
                     f"suggests anchoring bias (no recalibration against outcomes).",
            metric=stdev,
            threshold=0.05
        )
    return None


def detect_contradiction_suppression(entries: List[MemoryEntry]) -> Optional[ManipulationSignal]:
    """Detect if entries tagged 'contradicts' or 'negative' are scored lower."""
    negative_tags = {'contradicts', 'negative', 'error', 'mistake', 'wrong', 'failure'}
    
    negative = [e for e in entries if negative_tags & set(e.tags)]
    positive = [e for e in entries if not (negative_tags & set(e.tags)) and e.tags]
    
    if len(negative) < 2 or len(positive) < 2:
        return None
    
    neg_mean = statistics.mean([e.poignancy for e in negative])
    pos_mean = statistics.mean([e.poignancy for e in positive])
    gap = pos_mean - neg_mean
    
    neg_eviction_rate = sum(1 for e in negative if e.evicted) / len(negative)
    pos_eviction_rate = sum(1 for e in positive if e.evicted) / len(positive) if positive else 0
    
    if gap > 0.2 and neg_eviction_rate > pos_eviction_rate + 0.3:
        return ManipulationSignal(
            pattern="contradiction_suppression",
            severity="CRITICAL",
            evidence=f"Negative-tagged: mean poignancy={neg_mean:.3f}, eviction rate={neg_eviction_rate:.1%}. "
                     f"Positive-tagged: mean={pos_mean:.3f}, eviction rate={pos_eviction_rate:.1%}. "
                     f"Motivated forgetting pattern (Anderson & Hanslmayr 2014).",
            metric=gap,
            threshold=0.2
        )
    return None


def run_audit(entries: List[MemoryEntry]) -> dict:
    """Run all manipulation detectors."""
    signals = []
    
    for detector in [detect_inflation_drift, detect_selective_eviction, 
                     detect_score_clustering, detect_contradiction_suppression]:
        result = detector(entries)
        if result:
            signals.append(asdict(result))
    
    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    max_severity = max((s["severity"] for s in signals), 
                       key=lambda s: severity_order.get(s, 0), default="NONE")
    
    # Grade
    grade_map = {"NONE": "A", "LOW": "B", "MEDIUM": "C", "HIGH": "D", "CRITICAL": "F"}
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entries_analyzed": len(entries),
        "evicted_count": sum(1 for e in entries if e.evicted),
        "retained_count": sum(1 for e in entries if not e.evicted),
        "signals": signals,
        "signal_count": len(signals),
        "max_severity": max_severity,
        "grade": grade_map.get(max_severity, "C"),
        "recommendation": "External scoring or hash-chain eviction audits needed" if signals else "No manipulation detected"
    }


def demo():
    """Demo with synthetic manipulative agent."""
    import random
    random.seed(42)
    
    entries = []
    # Generate entries: agent inflates supportive memories, deflates contradictions
    for i in range(30):
        is_negative = random.random() < 0.3
        tags = ["error", "contradicts"] if is_negative else ["success", "insight"]
        # Manipulative scoring: negative stuff scored lower
        poignancy = random.uniform(0.1, 0.4) if is_negative else random.uniform(0.6, 0.95)
        # Negative entries more likely evicted
        evicted = is_negative and random.random() < 0.7
        
        entries.append(MemoryEntry(
            id=f"mem_{i:03d}",
            content_hash=hashlib.sha256(f"content_{i}".encode()).hexdigest()[:16],
            poignancy=poignancy,
            created_at=f"2026-03-{(i // 3) + 1:02d}T{(i % 24):02d}:00:00Z",
            evicted=evicted,
            evicted_at=f"2026-03-{(i // 3) + 2:02d}T00:00:00Z" if evicted else None,
            tags=tags
        ))
    
    # Add inflation drift: later entries scored higher
    for i, e in enumerate(sorted(entries, key=lambda x: x.created_at)):
        e.poignancy = min(1.0, e.poignancy + i * 0.01)
    
    result = run_audit(entries)
    
    print("=" * 55)
    print("POIGNANCY MANIPULATION AUDIT")
    print("=" * 55)
    print(f"Entries: {result['entries_analyzed']} "
          f"(retained: {result['retained_count']}, evicted: {result['evicted_count']})")
    print(f"Grade: {result['grade']} | Signals: {result['signal_count']}")
    print()
    
    for s in result["signals"]:
        print(f"[{s['severity']}] {s['pattern']}")
        print(f"  {s['evidence']}")
        print()
    
    print(f"Recommendation: {result['recommendation']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Poignancy manipulation detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Would load real entries from memory files
        print(json.dumps({"error": "Pass --demo or provide entries via stdin"}, indent=2))
    else:
        demo()
