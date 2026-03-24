#!/usr/bin/env python3
"""
temporal-beacon-validator.py — Roughtime-inspired temporal anchoring for ATF receipts.

Per skinner: "temporal beacon to anchor the 'now' so the resident can't be
retroactively edited out of the history."

Google Roughtime (2016): signed timestamps from multiple independent sources.
Disagreement between sources = attack signal.

ATF parallel: receipts carry timestamps from BOTH parties. Clock skew between
agent and counterparty is normal (bounded). Clock manipulation is detectable
via multi-source comparison.

Three validators:
  1. Bilateral timestamp consistency (agent vs counterparty)
  2. Temporal beacon cross-reference (external time sources)
  3. Retroactive insertion detection (sequence + timestamp monotonicity)
"""

import hashlib
import time
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TemporalVerdict(Enum):
    ANCHORED = "ANCHORED"       # Timestamps consistent, externally verified
    SKEWED = "SKEWED"           # Normal clock drift, within tolerance
    SUSPICIOUS = "SUSPICIOUS"   # Drift exceeds tolerance
    MANIPULATED = "MANIPULATED" # Evidence of retroactive insertion
    UNANCHORED = "UNANCHORED"   # No external reference available


# SPEC_CONSTANTS
MAX_BILATERAL_SKEW_SEC = 30     # Max acceptable skew between agent/counterparty
MAX_BEACON_DRIFT_SEC = 5        # Max drift from external time beacon
MONOTONICITY_TOLERANCE_SEC = 1  # Allow 1s reordering (network jitter)
MIN_BEACON_SOURCES = 2          # Roughtime requires 2+ independent sources


@dataclass
class TimestampedReceipt:
    receipt_id: str
    agent_timestamp: float       # Agent's claimed time
    counterparty_timestamp: float  # Counterparty's claimed time
    sequence_number: int
    beacon_timestamps: list[float]  # External beacon readings (0+ sources)
    prev_receipt_hash: str


@dataclass
class TemporalAudit:
    receipt_id: str
    verdict: TemporalVerdict
    bilateral_skew_sec: float
    beacon_drift_sec: Optional[float]
    monotonic: bool
    details: str


def validate_bilateral(receipt: TimestampedReceipt) -> tuple[bool, float, str]:
    """Check agent/counterparty timestamp consistency."""
    skew = abs(receipt.agent_timestamp - receipt.counterparty_timestamp)
    if skew <= MAX_BILATERAL_SKEW_SEC:
        return True, skew, f"bilateral skew {skew:.1f}s within {MAX_BILATERAL_SKEW_SEC}s tolerance"
    else:
        return False, skew, f"bilateral skew {skew:.1f}s EXCEEDS {MAX_BILATERAL_SKEW_SEC}s tolerance"


def validate_beacon(receipt: TimestampedReceipt) -> tuple[bool, Optional[float], str]:
    """Cross-reference against external time beacons (Roughtime model)."""
    if len(receipt.beacon_timestamps) < MIN_BEACON_SOURCES:
        return True, None, f"only {len(receipt.beacon_timestamps)} beacon(s), need {MIN_BEACON_SOURCES} for verification"
    
    # Check beacon agreement first (disagreement = attack on beacons)
    beacon_spread = max(receipt.beacon_timestamps) - min(receipt.beacon_timestamps)
    if beacon_spread > MAX_BEACON_DRIFT_SEC * 2:
        return False, beacon_spread, f"beacon disagreement {beacon_spread:.1f}s — possible beacon compromise"
    
    # Check receipt timestamp against beacon median
    beacon_median = statistics.median(receipt.beacon_timestamps)
    agent_drift = abs(receipt.agent_timestamp - beacon_median)
    cp_drift = abs(receipt.counterparty_timestamp - beacon_median)
    max_drift = max(agent_drift, cp_drift)
    
    if max_drift <= MAX_BEACON_DRIFT_SEC:
        return True, max_drift, f"beacon drift {max_drift:.1f}s within {MAX_BEACON_DRIFT_SEC}s"
    else:
        return False, max_drift, f"beacon drift {max_drift:.1f}s EXCEEDS {MAX_BEACON_DRIFT_SEC}s"


def validate_monotonicity(receipts: list[TimestampedReceipt]) -> list[tuple[int, str]]:
    """Detect retroactive insertion via sequence/timestamp monotonicity."""
    violations = []
    for i in range(1, len(receipts)):
        prev = receipts[i-1]
        curr = receipts[i]
        
        # Sequence must be strictly increasing
        if curr.sequence_number <= prev.sequence_number:
            violations.append((i, f"sequence regression: {curr.sequence_number} <= {prev.sequence_number}"))
        
        # Timestamps must be non-decreasing (within tolerance)
        time_diff = curr.agent_timestamp - prev.agent_timestamp
        if time_diff < -MONOTONICITY_TOLERANCE_SEC:
            violations.append((i, f"timestamp regression: {time_diff:.1f}s backwards"))
        
        # Gap analysis: suspiciously small gap between high sequence numbers
        if curr.sequence_number - prev.sequence_number > 1:
            expected_gap = (curr.sequence_number - prev.sequence_number) * 60  # ~1min per receipt
            actual_gap = curr.agent_timestamp - prev.agent_timestamp
            if actual_gap < expected_gap * 0.1:  # Less than 10% expected time
                violations.append((i, f"temporal compression: {curr.sequence_number - prev.sequence_number} "
                                    f"receipts in {actual_gap:.0f}s (expected ~{expected_gap:.0f}s)"))
    
    return violations


def audit_receipt(receipt: TimestampedReceipt, prev_receipts: list[TimestampedReceipt]) -> TemporalAudit:
    """Full temporal audit of a single receipt."""
    bilateral_ok, skew, bilateral_detail = validate_bilateral(receipt)
    beacon_ok, drift, beacon_detail = validate_beacon(receipt)
    
    all_receipts = prev_receipts + [receipt]
    violations = validate_monotonicity(all_receipts)
    monotonic = len(violations) == 0
    
    # Determine verdict
    if not monotonic:
        verdict = TemporalVerdict.MANIPULATED
        details = f"monotonicity violations: {[v[1] for v in violations]}"
    elif not bilateral_ok:
        verdict = TemporalVerdict.SUSPICIOUS
        details = bilateral_detail
    elif not beacon_ok and drift is not None:
        verdict = TemporalVerdict.SUSPICIOUS
        details = beacon_detail
    elif drift is None:
        verdict = TemporalVerdict.UNANCHORED if not bilateral_ok else TemporalVerdict.SKEWED
        details = f"{bilateral_detail}; {beacon_detail}"
    elif skew <= 5 and (drift is None or drift <= 2):
        verdict = TemporalVerdict.ANCHORED
        details = f"{bilateral_detail}; {beacon_detail}"
    else:
        verdict = TemporalVerdict.SKEWED
        details = f"{bilateral_detail}; {beacon_detail}"
    
    return TemporalAudit(
        receipt_id=receipt.receipt_id,
        verdict=verdict,
        bilateral_skew_sec=skew,
        beacon_drift_sec=drift,
        monotonic=monotonic,
        details=details
    )


# === Scenarios ===

def scenario_clean():
    """Well-behaved agents with synced clocks."""
    print("=== Scenario: Clean (synced clocks, beacons agree) ===")
    now = time.time()
    r = TimestampedReceipt("r001", now, now + 0.5, 1, [now + 0.2, now + 0.3, now + 0.1], "genesis")
    audit = audit_receipt(r, [])
    print(f"  Verdict: {audit.verdict.value}")
    print(f"  Bilateral skew: {audit.bilateral_skew_sec:.1f}s")
    print(f"  Beacon drift: {audit.beacon_drift_sec:.1f}s")
    print(f"  Monotonic: {audit.monotonic}")
    print()


def scenario_clock_drift():
    """Normal clock drift between agents."""
    print("=== Scenario: Clock Drift (within tolerance) ===")
    now = time.time()
    r = TimestampedReceipt("r002", now, now + 15, 1, [now + 1, now + 2], "genesis")
    audit = audit_receipt(r, [])
    print(f"  Verdict: {audit.verdict.value}")
    print(f"  Bilateral skew: {audit.bilateral_skew_sec:.1f}s")
    print(f"  Details: {audit.details}")
    print()


def scenario_timestamp_manipulation():
    """Agent backdates receipts to claim earlier interaction."""
    print("=== Scenario: Timestamp Manipulation (retroactive insertion) ===")
    now = time.time()
    prev = [
        TimestampedReceipt("r010", now - 100, now - 99, 10, [], "prev"),
        TimestampedReceipt("r011", now - 80, now - 79, 11, [], "r010"),
    ]
    # Inserted receipt claims to be between 10 and 11 but with sequence 12
    inserted = TimestampedReceipt("r012", now - 90, now - 89, 12, [now], "r011")
    audit = audit_receipt(inserted, prev)
    print(f"  Verdict: {audit.verdict.value}")
    print(f"  Monotonic: {audit.monotonic}")
    print(f"  Beacon drift: {audit.beacon_drift_sec}s (beacon says NOW, receipt says 90s ago)")
    print(f"  Details: {audit.details}")
    print()


def scenario_beacon_disagreement():
    """External beacons disagree — possible beacon compromise."""
    print("=== Scenario: Beacon Disagreement (compromise signal) ===")
    now = time.time()
    r = TimestampedReceipt("r003", now, now + 1, 1, [now, now + 30, now + 1], "genesis")
    audit = audit_receipt(r, [])
    print(f"  Verdict: {audit.verdict.value}")
    print(f"  Beacon drift: {audit.beacon_drift_sec:.1f}s")
    print(f"  Details: {audit.details}")
    print()


def scenario_no_beacons():
    """No external beacons available — bilateral only."""
    print("=== Scenario: No Beacons (bilateral only) ===")
    now = time.time()
    r = TimestampedReceipt("r004", now, now + 2, 1, [], "genesis")
    audit = audit_receipt(r, [])
    print(f"  Verdict: {audit.verdict.value}")
    print(f"  Beacon drift: {audit.beacon_drift_sec}")
    print(f"  Details: {audit.details}")
    print()


if __name__ == "__main__":
    print("Temporal Beacon Validator — Roughtime-Inspired Anchoring for ATF")
    print("Per skinner + Google Roughtime (2016)")
    print("=" * 65)
    print()
    scenario_clean()
    scenario_clock_drift()
    scenario_timestamp_manipulation()
    scenario_beacon_disagreement()
    scenario_no_beacons()
    
    print("=" * 65)
    print("KEY INSIGHTS:")
    print("1. Bilateral timestamps = minimum viable temporal anchor")
    print("2. External beacons (Roughtime) = verifiable time reference")
    print("3. Beacon disagreement = attack signal, not data quality issue")
    print("4. Monotonicity violations = retroactive insertion detected")
    print("5. Clock skew is normal. Clock manipulation is not.")
