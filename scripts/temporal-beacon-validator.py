#!/usr/bin/env python3
"""
temporal-beacon-validator.py — Validate temporal anchoring of ATF receipts.

Per skinner: "We need that temporal beacon to anchor the 'now' so the resident
can't be retroactively edited out of the history."

Per Haber & Stornetta (1991): linked timestamping where altering one entry
requires rewriting the entire chain downstream.

Three temporal anchor sources (decreasing trust):
  1. COUNTERPARTY timestamp (external, non-self-attested)
  2. K-of-N witness timestamps (distributed consensus on "now")
  3. SELF timestamp (weakest, gameable)

Validates:
  - Timestamp consistency across sources
  - Clock skew detection
  - Retroactive insertion detection via hash chain gaps
  - Temporal ordering violations
"""

import hashlib
import time
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AnchorSource(Enum):
    COUNTERPARTY = "COUNTERPARTY"  # Strongest: other party timestamps
    WITNESS_QUORUM = "WITNESS_QUORUM"  # K-of-N independent timestamps
    SELF = "SELF"  # Weakest: self-reported


class TemporalVerdict(Enum):
    ANCHORED = "ANCHORED"           # Timestamps consistent, externally verified
    SKEWED = "SKEWED"               # Clock drift detected but within tolerance
    SUSPICIOUS = "SUSPICIOUS"       # Ordering violation or large skew
    RETROACTIVE = "RETROACTIVE"     # Evidence of backdated insertion
    UNANCHORED = "UNANCHORED"       # Self-timestamp only, no external anchor


# SPEC_CONSTANTS
MAX_SKEW_SECONDS = 300          # 5 min tolerance between sources
WITNESS_QUORUM_MIN = 2          # Minimum witnesses for WITNESS_QUORUM anchor
ORDERING_VIOLATION_THRESHOLD = 1  # Seconds of backward time allowed (clock jitter)
CHAIN_GAP_SUSPICIOUS = 3600     # 1 hour gap in otherwise regular chain = suspicious


@dataclass
class TimestampBundle:
    """All timestamps associated with a single receipt."""
    receipt_hash: str
    self_timestamp: float
    counterparty_timestamp: Optional[float] = None
    witness_timestamps: list[float] = field(default_factory=list)
    prev_receipt_hash: Optional[str] = None
    chain_hash: Optional[str] = None


@dataclass
class TemporalAudit:
    receipt_hash: str
    verdict: str
    anchor_source: str
    skew_seconds: float
    details: dict


def compute_chain_hash(receipt_hash: str, prev_hash: str, timestamp: float) -> str:
    """Haber & Stornetta linked timestamping."""
    data = f"{prev_hash}:{receipt_hash}:{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def determine_anchor(bundle: TimestampBundle) -> tuple[AnchorSource, float]:
    """Determine best temporal anchor and reference timestamp."""
    if bundle.counterparty_timestamp is not None:
        return AnchorSource.COUNTERPARTY, bundle.counterparty_timestamp
    
    if len(bundle.witness_timestamps) >= WITNESS_QUORUM_MIN:
        # Median of witness timestamps = consensus "now"
        median_ts = statistics.median(bundle.witness_timestamps)
        return AnchorSource.WITNESS_QUORUM, median_ts
    
    return AnchorSource.SELF, bundle.self_timestamp


def validate_timestamp(bundle: TimestampBundle) -> TemporalAudit:
    """Validate temporal anchoring of a single receipt."""
    anchor_source, reference_ts = determine_anchor(bundle)
    skew = abs(bundle.self_timestamp - reference_ts)
    
    details = {
        "self_timestamp": bundle.self_timestamp,
        "reference_timestamp": reference_ts,
        "anchor_source": anchor_source.value,
        "skew_seconds": round(skew, 2),
    }
    
    # Check witness agreement if available
    if bundle.witness_timestamps:
        witness_spread = max(bundle.witness_timestamps) - min(bundle.witness_timestamps)
        details["witness_count"] = len(bundle.witness_timestamps)
        details["witness_spread_seconds"] = round(witness_spread, 2)
        
        if witness_spread > MAX_SKEW_SECONDS:
            details["witness_disagreement"] = True
    
    # Determine verdict
    if anchor_source == AnchorSource.SELF:
        verdict = TemporalVerdict.UNANCHORED
    elif skew <= ORDERING_VIOLATION_THRESHOLD:
        verdict = TemporalVerdict.ANCHORED
    elif skew <= MAX_SKEW_SECONDS:
        verdict = TemporalVerdict.SKEWED
    else:
        verdict = TemporalVerdict.SUSPICIOUS
    
    return TemporalAudit(
        receipt_hash=bundle.receipt_hash,
        verdict=verdict.value,
        anchor_source=anchor_source.value,
        skew_seconds=round(skew, 2),
        details=details
    )


def detect_retroactive_insertion(bundles: list[TimestampBundle]) -> list[dict]:
    """Detect receipts inserted out of temporal order (backdating)."""
    violations = []
    
    for i in range(1, len(bundles)):
        prev = bundles[i - 1]
        curr = bundles[i]
        
        # Self-timestamps should be monotonically increasing
        if curr.self_timestamp < prev.self_timestamp - ORDERING_VIOLATION_THRESHOLD:
            violations.append({
                "type": "TEMPORAL_ORDERING_VIOLATION",
                "receipt": curr.receipt_hash,
                "prev_receipt": prev.receipt_hash,
                "time_delta": round(curr.self_timestamp - prev.self_timestamp, 2),
                "severity": "CRITICAL" if abs(curr.self_timestamp - prev.self_timestamp) > 3600 else "WARNING"
            })
        
        # Check for suspicious gaps in otherwise regular chain
        if i >= 2:
            prev_gap = bundles[i-1].self_timestamp - bundles[i-2].self_timestamp
            curr_gap = curr.self_timestamp - prev.self_timestamp
            if prev_gap > 0 and curr_gap > 0:
                ratio = curr_gap / prev_gap if prev_gap > 0 else float('inf')
                if ratio > 10 and curr_gap > CHAIN_GAP_SUSPICIOUS:
                    violations.append({
                        "type": "SUSPICIOUS_GAP",
                        "receipt": curr.receipt_hash,
                        "gap_seconds": round(curr_gap, 0),
                        "expected_gap": round(prev_gap, 0),
                        "ratio": round(ratio, 1)
                    })
        
        # Verify chain hash continuity
        if curr.prev_receipt_hash and curr.prev_receipt_hash != prev.receipt_hash:
            violations.append({
                "type": "CHAIN_DISCONTINUITY",
                "receipt": curr.receipt_hash,
                "expected_prev": prev.receipt_hash,
                "actual_prev": curr.prev_receipt_hash,
                "severity": "CRITICAL"
            })
    
    return violations


def audit_chain(bundles: list[TimestampBundle]) -> dict:
    """Full temporal audit of a receipt chain."""
    audits = [validate_timestamp(b) for b in bundles]
    violations = detect_retroactive_insertion(bundles)
    
    verdict_counts = {}
    for a in audits:
        verdict_counts[a.verdict] = verdict_counts.get(a.verdict, 0) + 1
    
    anchor_counts = {}
    for a in audits:
        anchor_counts[a.anchor_source] = anchor_counts.get(a.anchor_source, 0) + 1
    
    avg_skew = statistics.mean(a.skew_seconds for a in audits) if audits else 0
    
    # Overall chain grade
    if violations and any(v.get("severity") == "CRITICAL" for v in violations):
        chain_grade = "F"
    elif verdict_counts.get("SUSPICIOUS", 0) > 0:
        chain_grade = "D"
    elif verdict_counts.get("UNANCHORED", 0) > len(audits) * 0.5:
        chain_grade = "C"
    elif verdict_counts.get("SKEWED", 0) > len(audits) * 0.3:
        chain_grade = "B"
    else:
        chain_grade = "A"
    
    return {
        "total_receipts": len(bundles),
        "chain_grade": chain_grade,
        "verdict_distribution": verdict_counts,
        "anchor_distribution": anchor_counts,
        "avg_skew_seconds": round(avg_skew, 2),
        "violations": violations,
        "violation_count": len(violations)
    }


# === Scenarios ===

def scenario_well_anchored():
    """Properly anchored chain with counterparty timestamps."""
    print("=== Scenario: Well-Anchored Chain ===")
    now = time.time()
    bundles = []
    prev_hash = "genesis"
    for i in range(10):
        ts = now + i * 60  # 1 min apart
        h = f"receipt_{i:03d}"
        bundles.append(TimestampBundle(
            receipt_hash=h,
            self_timestamp=ts,
            counterparty_timestamp=ts + 0.5,  # 500ms skew = normal
            witness_timestamps=[ts + 0.3, ts + 0.7, ts + 0.4],
            prev_receipt_hash=prev_hash
        ))
        prev_hash = h
    
    result = audit_chain(bundles)
    print(f"  Grade: {result['chain_grade']}")
    print(f"  Verdicts: {result['verdict_distribution']}")
    print(f"  Anchors: {result['anchor_distribution']}")
    print(f"  Avg skew: {result['avg_skew_seconds']}s")
    print(f"  Violations: {result['violation_count']}")
    print()


def scenario_self_only():
    """No external anchoring — self-timestamps only."""
    print("=== Scenario: Self-Timestamp Only (Unanchored) ===")
    now = time.time()
    bundles = [
        TimestampBundle(receipt_hash=f"r{i}", self_timestamp=now + i * 120,
                        prev_receipt_hash=f"r{i-1}" if i > 0 else "genesis")
        for i in range(10)
    ]
    
    result = audit_chain(bundles)
    print(f"  Grade: {result['chain_grade']}")
    print(f"  Verdicts: {result['verdict_distribution']}")
    print(f"  Key: UNANCHORED = self-attested only, no external verification")
    print()


def scenario_backdated_insertion():
    """Retroactive insertion — timestamps go backward."""
    print("=== Scenario: Backdated Insertion (Attack) ===")
    now = time.time()
    bundles = [
        TimestampBundle("r0", now, counterparty_timestamp=now + 0.1, prev_receipt_hash="genesis"),
        TimestampBundle("r1", now + 60, counterparty_timestamp=now + 60.2, prev_receipt_hash="r0"),
        TimestampBundle("r_injected", now - 3600, counterparty_timestamp=now - 3600,
                        prev_receipt_hash="r1"),  # BACKDATED 1 hour
        TimestampBundle("r2", now + 120, counterparty_timestamp=now + 120.1, prev_receipt_hash="r_injected"),
    ]
    
    result = audit_chain(bundles)
    print(f"  Grade: {result['chain_grade']}")
    print(f"  Violations: {result['violations']}")
    print(f"  Key: Temporal ordering violation correctly caught")
    print()


def scenario_clock_skew():
    """Moderate clock skew between agent and counterparty."""
    print("=== Scenario: Clock Skew (Legitimate Drift) ===")
    now = time.time()
    bundles = [
        TimestampBundle(f"r{i}", now + i * 60,
                        counterparty_timestamp=now + i * 60 + 45,  # 45s skew
                        prev_receipt_hash=f"r{i-1}" if i > 0 else "genesis")
        for i in range(10)
    ]
    
    result = audit_chain(bundles)
    print(f"  Grade: {result['chain_grade']}")
    print(f"  Verdicts: {result['verdict_distribution']}")
    print(f"  Avg skew: {result['avg_skew_seconds']}s (within {MAX_SKEW_SECONDS}s tolerance)")
    print()


def scenario_witness_disagreement():
    """Witnesses disagree on timestamp — split-brain detection."""
    print("=== Scenario: Witness Disagreement ===")
    now = time.time()
    bundles = [
        TimestampBundle("r0", now,
                        witness_timestamps=[now + 1, now + 2, now + 500],  # 500s spread
                        prev_receipt_hash="genesis"),
    ]
    
    result = audit_chain(bundles)
    audit = validate_timestamp(bundles[0])
    print(f"  Grade: {result['chain_grade']}")
    print(f"  Witness disagreement: {audit.details.get('witness_disagreement', False)}")
    print(f"  Witness spread: {audit.details.get('witness_spread_seconds', 0)}s")
    print(f"  Key: Large witness spread = potential split-brain or compromised witness")
    print()


if __name__ == "__main__":
    print("Temporal Beacon Validator — Receipt Timestamping Integrity for ATF")
    print("Per skinner + Haber & Stornetta (1991)")
    print("=" * 70)
    print()
    scenario_well_anchored()
    scenario_self_only()
    scenario_backdated_insertion()
    scenario_clock_skew()
    scenario_witness_disagreement()
    
    print("=" * 70)
    print("KEY INSIGHT: Counterparty timestamps > witness quorum > self-report.")
    print("Hash chain makes retroactive insertion detectable.")
    print("Self-only = UNANCHORED. External anchor = temporal proof of work.")
