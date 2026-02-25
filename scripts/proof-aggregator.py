#!/usr/bin/env python3
"""
proof-aggregator.py — Aggregate N independent receipts into 1 confidence score.

Takes multiple attestation receipts from different sources (DKIM, on-chain tx, 
generation signatures, isnad envelopes) and produces a weighted confidence score.

Weights:
- Source diversity: different proof types matter more than many of same type
- Temporal spread: receipts clustered in time = suspicious (sybil)
- Attester independence: unique attesters weighted higher than repeat
- Receipt freshness: decay over time

Input: JSON array of receipts
Output: Confidence score 0.0-1.0 with breakdown

Usage:
    python proof-aggregator.py demo
    python proof-aggregator.py score FILE.json
    echo '[...]' | python proof-aggregator.py stdin
"""

import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Receipt:
    """A single attestation receipt from any source."""
    source: str          # "dkim", "x402", "generation_sig", "isnad", "paylock"
    receipt_type: str    # "delivery", "payment", "attestation", "verification"  
    hash: str            # Content hash or tx hash
    timestamp: str       # ISO timestamp
    attester_id: str     # Who attested
    metadata: dict = field(default_factory=dict)


@dataclass
class AggregationResult:
    """Result of proof aggregation."""
    confidence: float          # 0.0 - 1.0
    source_diversity: float    # How many different proof types
    temporal_health: float     # 1.0 = spread out, 0.0 = suspicious cluster
    attester_independence: float  # Unique attesters ratio
    freshness: float           # How recent
    receipt_count: int
    breakdown: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


class ProofAggregator:
    """Aggregates multiple receipts into a confidence score."""
    
    # Known proof source types and their base reliability weights
    SOURCE_WEIGHTS = {
        "dkim": 0.7,           # Cryptographic, but depends on h= scope
        "x402": 0.9,           # On-chain, verifiable
        "generation_sig": 0.8, # Signed at creation time
        "isnad": 0.6,          # Attestation chain, depends on chain length
        "paylock": 0.85,       # Escrow-backed verification
        "manual": 0.3,         # Human assertion, no crypto proof
    }
    
    # Weights for final score composition
    SCORE_WEIGHTS = {
        "source_diversity": 0.30,
        "temporal_health": 0.20,
        "attester_independence": 0.25,
        "freshness": 0.15,
        "volume": 0.10,
    }
    
    # Freshness half-life in hours
    FRESHNESS_HALFLIFE_HOURS = 168  # 1 week
    
    def __init__(self, sybil_cv_threshold: float = 0.5):
        self.sybil_cv_threshold = sybil_cv_threshold
    
    def aggregate(self, receipts: list[Receipt], 
                  reference_time: Optional[datetime] = None) -> AggregationResult:
        """Aggregate receipts into a confidence score."""
        if not receipts:
            return AggregationResult(
                confidence=0.0, source_diversity=0.0, temporal_health=0.0,
                attester_independence=0.0, freshness=0.0, receipt_count=0,
                warnings=["No receipts provided"]
            )
        
        ref_time = reference_time or datetime.now(timezone.utc)
        
        # 1. Source diversity: Shannon entropy of source types
        source_counts = Counter(r.source for r in receipts)
        source_diversity = self._shannon_diversity(source_counts, len(self.SOURCE_WEIGHTS))
        
        # 2. Temporal health: coefficient of variation of inter-receipt intervals
        temporal_health = self._temporal_health(receipts)
        
        # 3. Attester independence: unique attesters / total receipts
        attester_counts = Counter(r.attester_id for r in receipts)
        unique_ratio = len(attester_counts) / len(receipts)
        # Bonus for attesters from different sources
        cross_source = self._cross_source_attesters(receipts)
        attester_independence = min(1.0, unique_ratio * 0.7 + cross_source * 0.3)
        
        # 4. Freshness: exponential decay from reference time
        freshness = self._freshness(receipts, ref_time)
        
        # 5. Volume: logarithmic scaling (diminishing returns)
        volume = min(1.0, math.log2(len(receipts) + 1) / math.log2(10))
        
        # Weighted combination
        confidence = (
            self.SCORE_WEIGHTS["source_diversity"] * source_diversity +
            self.SCORE_WEIGHTS["temporal_health"] * temporal_health +
            self.SCORE_WEIGHTS["attester_independence"] * attester_independence +
            self.SCORE_WEIGHTS["freshness"] * freshness +
            self.SCORE_WEIGHTS["volume"] * volume
        )
        
        # Apply source reliability modifier
        avg_source_reliability = sum(
            self.SOURCE_WEIGHTS.get(r.source, 0.3) for r in receipts
        ) / len(receipts)
        confidence *= avg_source_reliability
        
        # Warnings
        warnings = []
        if len(receipts) < 3:
            warnings.append(f"Low receipt count ({len(receipts)}). Minimum 3 recommended.")
        if temporal_health < 0.3:
            warnings.append("Temporal clustering detected. Possible sybil pattern.")
        if attester_independence < 0.5:
            warnings.append("Low attester diversity. Many repeat attesters.")
        if source_diversity < 0.3:
            warnings.append("Low source diversity. Single proof type dominates.")
        
        return AggregationResult(
            confidence=round(min(1.0, confidence), 4),
            source_diversity=round(source_diversity, 4),
            temporal_health=round(temporal_health, 4),
            attester_independence=round(attester_independence, 4),
            freshness=round(freshness, 4),
            receipt_count=len(receipts),
            breakdown={
                "sources": dict(source_counts),
                "attesters": dict(attester_counts),
                "avg_source_reliability": round(avg_source_reliability, 4),
                "cross_source_attesters": round(cross_source, 4),
            },
            warnings=warnings,
        )
    
    def _shannon_diversity(self, counts: Counter, max_categories: int) -> float:
        """Normalized Shannon entropy. 1.0 = perfectly even distribution."""
        total = sum(counts.values())
        if total == 0 or len(counts) <= 1:
            return 0.0 if len(counts) <= 1 else 1.0
        
        entropy = -sum(
            (c / total) * math.log2(c / total) 
            for c in counts.values() if c > 0
        )
        max_entropy = math.log2(min(len(counts), max_categories))
        return entropy / max_entropy if max_entropy > 0 else 0.0
    
    def _temporal_health(self, receipts: list[Receipt]) -> float:
        """Score temporal distribution. High CV = good spread. Low CV = suspicious cluster."""
        if len(receipts) < 2:
            return 0.5  # Not enough data
        
        timestamps = sorted(self._parse_ts(r.timestamp) for r in receipts)
        intervals = [
            (timestamps[i+1] - timestamps[i]).total_seconds()
            for i in range(len(timestamps) - 1)
        ]
        
        if not intervals or all(i == 0 for i in intervals):
            return 0.1  # All same timestamp = very suspicious
        
        mean = sum(intervals) / len(intervals)
        if mean == 0:
            return 0.1
        
        variance = sum((i - mean) ** 2 for i in intervals) / len(intervals)
        cv = math.sqrt(variance) / mean
        
        # CV > threshold = healthy spread, CV < threshold = cluster
        if cv > self.sybil_cv_threshold:
            return min(1.0, 0.5 + cv * 0.25)
        else:
            return max(0.1, cv / self.sybil_cv_threshold * 0.5)
    
    def _cross_source_attesters(self, receipts: list[Receipt]) -> float:
        """Fraction of attesters appearing across multiple source types."""
        attester_sources: dict[str, set] = {}
        for r in receipts:
            attester_sources.setdefault(r.attester_id, set()).add(r.source)
        
        if not attester_sources:
            return 0.0
        
        cross = sum(1 for sources in attester_sources.values() if len(sources) > 1)
        return cross / len(attester_sources)
    
    def _freshness(self, receipts: list[Receipt], ref_time: datetime) -> float:
        """Average freshness with exponential decay."""
        scores = []
        for r in receipts:
            ts = self._parse_ts(r.timestamp)
            age_hours = (ref_time - ts).total_seconds() / 3600
            score = math.exp(-0.693 * age_hours / self.FRESHNESS_HALFLIFE_HOURS)
            scores.append(score)
        return sum(scores) / len(scores)
    
    @staticmethod
    def _parse_ts(ts: str) -> datetime:
        """Parse ISO timestamp."""
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)


def demo():
    """Run demo with synthetic receipts mimicking tc3."""
    print("=" * 60)
    print("Proof Aggregator Demo — Test Case 3 Simulation")
    print("=" * 60)
    
    aggregator = ProofAggregator()
    
    # Simulate tc3 receipts
    tc3_receipts = [
        Receipt(
            source="paylock",
            receipt_type="payment",
            hash="tx:0x1234...escrow_deposit",
            timestamp="2026-02-24T06:26:00Z",
            attester_id="gendolf",
            metadata={"amount": "0.01 SOL", "role": "funder"}
        ),
        Receipt(
            source="dkim",
            receipt_type="delivery",
            hash="sha256:f309922b...deliverable",
            timestamp="2026-02-24T07:06:00Z",
            attester_id="kit_fox",
            metadata={"subject": "Test Case 3 Deliverable"}
        ),
        Receipt(
            source="isnad",
            receipt_type="attestation",
            hash="sha256:bro_agent_review_092",
            timestamp="2026-02-24T07:46:00Z",
            attester_id="bro_agent",
            metadata={"score": 0.92, "role": "judge"}
        ),
        Receipt(
            source="isnad",
            receipt_type="attestation",
            hash="sha256:momo_attestation",
            timestamp="2026-02-24T08:00:00Z",
            attester_id="momo",
            metadata={"role": "independent_attester"}
        ),
        Receipt(
            source="isnad",
            receipt_type="attestation",
            hash="sha256:braindiff_attestation",
            timestamp="2026-02-24T10:28:00Z",
            attester_id="braindiff",
            metadata={"role": "independent_attester"}
        ),
    ]
    
    ref_time = datetime(2026, 2, 25, 3, 0, tzinfo=timezone.utc)
    result = aggregator.aggregate(tc3_receipts, ref_time)
    
    print(f"\nReceipts: {result.receipt_count}")
    print(f"Confidence: {result.confidence}")
    print(f"  Source diversity:       {result.source_diversity}")
    print(f"  Temporal health:        {result.temporal_health}")
    print(f"  Attester independence:  {result.attester_independence}")
    print(f"  Freshness:              {result.freshness}")
    print(f"\nBreakdown: {json.dumps(result.breakdown, indent=2)}")
    if result.warnings:
        print(f"\n⚠️ Warnings:")
        for w in result.warnings:
            print(f"  - {w}")
    
    # Compare: sybil-like pattern
    print("\n" + "=" * 60)
    print("Comparison: Sybil-like pattern (5 receipts, same attester, same second)")
    print("=" * 60)
    
    sybil_receipts = [
        Receipt(
            source="isnad",
            receipt_type="attestation",
            hash=f"sha256:fake_{i}",
            timestamp="2026-02-24T07:00:00Z",
            attester_id="sockpuppet",
        ) for i in range(5)
    ]
    
    sybil_result = aggregator.aggregate(sybil_receipts, ref_time)
    print(f"\nReceipts: {sybil_result.receipt_count}")
    print(f"Confidence: {sybil_result.confidence}")
    print(f"  Source diversity:       {sybil_result.source_diversity}")
    print(f"  Temporal health:        {sybil_result.temporal_health}")
    print(f"  Attester independence:  {sybil_result.attester_independence}")
    if sybil_result.warnings:
        print(f"\n⚠️ Warnings:")
        for w in sybil_result.warnings:
            print(f"  - {w}")
    
    # Healthy vs sybil comparison
    print(f"\n{'='*60}")
    print(f"TC3 confidence:   {result.confidence}")
    print(f"Sybil confidence: {sybil_result.confidence}")
    print(f"Discrimination:   {result.confidence - sybil_result.confidence:.4f}")


def score_file(filepath: str):
    """Score receipts from a JSON file."""
    with open(filepath) as f:
        data = json.load(f)
    
    receipts = [Receipt(**r) for r in data]
    aggregator = ProofAggregator()
    result = aggregator.aggregate(receipts)
    
    print(json.dumps({
        "confidence": result.confidence,
        "source_diversity": result.source_diversity,
        "temporal_health": result.temporal_health,
        "attester_independence": result.attester_independence,
        "freshness": result.freshness,
        "receipt_count": result.receipt_count,
        "breakdown": result.breakdown,
        "warnings": result.warnings,
    }, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "score" and len(sys.argv) > 2:
        score_file(sys.argv[2])
    elif sys.argv[1] == "stdin":
        data = json.load(sys.stdin)
        receipts = [Receipt(**r) for r in data]
        aggregator = ProofAggregator()
        result = aggregator.aggregate(receipts)
        print(json.dumps({"confidence": result.confidence, "warnings": result.warnings}))
    else:
        print(__doc__)
