#!/usr/bin/env python3
"""
write-time-injection-detector.py — Detect retroactive edits in ATF receipt chains.

Per skinner: "A single witness is a vulnerability; K-of-N is a distributed audit.
We need that temporal beacon to anchor the 'now' so the resident can't be
retroactively edited out of the history."

Write-time injection: an attacker inserts, modifies, or reorders receipts after
the fact. Detection relies on three properties:
  1. Causal ordering (Lamport 1978): happened-before is unforgeable
  2. K-of-N temporal witnesses: multiple independent timestamps
  3. Hash chain continuity: any break = tamper evidence

Attack patterns detected:
  - RETROACTIVE_INSERT: receipt timestamp < predecessor but hash references it
  - CAUSAL_VIOLATION: receipt references future events
  - WITNESS_DISAGREEMENT: K witnesses disagree on ordering by > threshold
  - HASH_CHAIN_BREAK: prev_hash doesn't match computed chain
  - TIMESTAMP_IMPOSSIBLE: receipt claims time before genesis or after now
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class InjectionType(Enum):
    RETROACTIVE_INSERT = "RETROACTIVE_INSERT"
    CAUSAL_VIOLATION = "CAUSAL_VIOLATION"
    WITNESS_DISAGREEMENT = "WITNESS_DISAGREEMENT"
    HASH_CHAIN_BREAK = "HASH_CHAIN_BREAK"
    TIMESTAMP_IMPOSSIBLE = "TIMESTAMP_IMPOSSIBLE"
    CLEAN = "CLEAN"


# SPEC_CONSTANTS
MAX_WITNESS_SKEW_SECONDS = 30  # Max acceptable timestamp disagreement
MIN_WITNESSES = 2               # Minimum temporal witnesses for validity
GENESIS_EPOCH = 1700000000      # Earliest valid timestamp (Nov 2023)


@dataclass
class TemporalWitness:
    """Independent timestamp attestation."""
    witness_id: str
    timestamp: float
    signature_hash: str


@dataclass
class Receipt:
    receipt_id: str
    agent_id: str
    timestamp: float
    prev_hash: str
    content_hash: str
    witnesses: list  # list of TemporalWitness
    metadata: dict = field(default_factory=dict)
    
    @property
    def receipt_hash(self) -> str:
        h = f"{self.receipt_id}:{self.timestamp}:{self.prev_hash}:{self.content_hash}"
        return hashlib.sha256(h.encode()).hexdigest()[:16]


@dataclass
class InjectionAlert:
    receipt_id: str
    injection_type: InjectionType
    severity: str  # CRITICAL, WARNING, INFO
    evidence: dict
    recommendation: str


def check_causal_ordering(chain: list[Receipt]) -> list[InjectionAlert]:
    """Check that timestamps are monotonically non-decreasing."""
    alerts = []
    for i in range(1, len(chain)):
        if chain[i].timestamp < chain[i-1].timestamp:
            alerts.append(InjectionAlert(
                receipt_id=chain[i].receipt_id,
                injection_type=InjectionType.RETROACTIVE_INSERT,
                severity="CRITICAL",
                evidence={
                    "this_timestamp": chain[i].timestamp,
                    "prev_timestamp": chain[i-1].timestamp,
                    "time_delta": chain[i].timestamp - chain[i-1].timestamp,
                    "position": i
                },
                recommendation="Receipt claims earlier time than predecessor. "
                               "Retroactive insertion detected. REJECT chain from this point."
            ))
    return alerts


def check_hash_chain(chain: list[Receipt]) -> list[InjectionAlert]:
    """Verify hash chain integrity."""
    alerts = []
    for i in range(1, len(chain)):
        expected_prev = chain[i-1].receipt_hash
        if chain[i].prev_hash != expected_prev:
            alerts.append(InjectionAlert(
                receipt_id=chain[i].receipt_id,
                injection_type=InjectionType.HASH_CHAIN_BREAK,
                severity="CRITICAL",
                evidence={
                    "expected_prev_hash": expected_prev,
                    "actual_prev_hash": chain[i].prev_hash,
                    "position": i
                },
                recommendation="Hash chain broken. Receipt references wrong predecessor. "
                               "Either insertion or deletion detected. QUARANTINE."
            ))
    return alerts


def check_witness_agreement(receipt: Receipt) -> list[InjectionAlert]:
    """Check that K temporal witnesses agree on timing."""
    alerts = []
    if len(receipt.witnesses) < MIN_WITNESSES:
        alerts.append(InjectionAlert(
            receipt_id=receipt.receipt_id,
            injection_type=InjectionType.WITNESS_DISAGREEMENT,
            severity="WARNING",
            evidence={
                "witness_count": len(receipt.witnesses),
                "minimum_required": MIN_WITNESSES
            },
            recommendation=f"Insufficient witnesses ({len(receipt.witnesses)}/{MIN_WITNESSES}). "
                           "Temporal anchoring weak. DEGRADE trust."
        ))
        return alerts
    
    timestamps = [w.timestamp for w in receipt.witnesses]
    max_skew = max(timestamps) - min(timestamps)
    
    if max_skew > MAX_WITNESS_SKEW_SECONDS:
        # Check if receipt's own timestamp is within witness range
        receipt_in_range = min(timestamps) <= receipt.timestamp <= max(timestamps)
        alerts.append(InjectionAlert(
            receipt_id=receipt.receipt_id,
            injection_type=InjectionType.WITNESS_DISAGREEMENT,
            severity="CRITICAL" if not receipt_in_range else "WARNING",
            evidence={
                "max_skew_seconds": max_skew,
                "threshold": MAX_WITNESS_SKEW_SECONDS,
                "witness_timestamps": timestamps,
                "receipt_timestamp": receipt.timestamp,
                "receipt_in_witness_range": receipt_in_range
            },
            recommendation="Temporal witnesses disagree beyond threshold. "
                           "Possible clock manipulation or network partition."
        ))
    
    return alerts


def check_timestamp_bounds(receipt: Receipt) -> list[InjectionAlert]:
    """Check timestamp is within valid bounds."""
    alerts = []
    now = time.time()
    
    if receipt.timestamp < GENESIS_EPOCH:
        alerts.append(InjectionAlert(
            receipt_id=receipt.receipt_id,
            injection_type=InjectionType.TIMESTAMP_IMPOSSIBLE,
            severity="CRITICAL",
            evidence={
                "timestamp": receipt.timestamp,
                "genesis_epoch": GENESIS_EPOCH,
                "claim": "before_genesis"
            },
            recommendation="Receipt claims time before genesis epoch. REJECT."
        ))
    
    if receipt.timestamp > now + 300:  # 5-minute future tolerance
        alerts.append(InjectionAlert(
            receipt_id=receipt.receipt_id,
            injection_type=InjectionType.TIMESTAMP_IMPOSSIBLE,
            severity="CRITICAL",
            evidence={
                "timestamp": receipt.timestamp,
                "current_time": now,
                "future_offset_seconds": receipt.timestamp - now,
                "claim": "future_receipt"
            },
            recommendation="Receipt claims future time beyond tolerance. "
                           "Clock manipulation or pre-dated injection. REJECT."
        ))
    
    return alerts


def audit_chain(chain: list[Receipt]) -> dict:
    """Full audit of a receipt chain for write-time injection."""
    all_alerts = []
    
    # Chain-level checks
    all_alerts.extend(check_causal_ordering(chain))
    all_alerts.extend(check_hash_chain(chain))
    
    # Per-receipt checks
    for receipt in chain:
        all_alerts.extend(check_witness_agreement(receipt))
        all_alerts.extend(check_timestamp_bounds(receipt))
    
    critical = [a for a in all_alerts if a.severity == "CRITICAL"]
    warnings = [a for a in all_alerts if a.severity == "WARNING"]
    
    if critical:
        verdict = "INJECTION_DETECTED"
        grade = "F"
    elif warnings:
        verdict = "SUSPICIOUS"
        grade = "C"
    else:
        verdict = "CLEAN"
        grade = "A"
    
    return {
        "chain_length": len(chain),
        "verdict": verdict,
        "grade": grade,
        "critical_alerts": len(critical),
        "warning_alerts": len(warnings),
        "alerts": [
            {
                "receipt": a.receipt_id,
                "type": a.injection_type.value,
                "severity": a.severity,
                "evidence": a.evidence
            }
            for a in all_alerts
        ],
        "injection_types_detected": list(set(a.injection_type.value for a in all_alerts))
    }


def make_witness(witness_id: str, timestamp: float) -> TemporalWitness:
    sig = hashlib.sha256(f"{witness_id}:{timestamp}".encode()).hexdigest()[:8]
    return TemporalWitness(witness_id, timestamp, sig)


# === Scenarios ===

def scenario_clean_chain():
    """Normal chain with proper witnesses."""
    print("=== Scenario 1: Clean Chain ===")
    now = time.time()
    
    chain = []
    prev = "genesis"
    for i in range(5):
        t = now - 300 + i * 60
        r = Receipt(
            f"r{i:03d}", "kit_fox", t, prev, f"content_{i}",
            [make_witness("w1", t + 1), make_witness("w2", t + 2)]
        )
        prev = r.receipt_hash
        chain.append(r)
    
    result = audit_chain(chain)
    print(f"  Verdict: {result['verdict']} (Grade {result['grade']})")
    print(f"  Alerts: {result['critical_alerts']} critical, {result['warning_alerts']} warnings")
    print()


def scenario_retroactive_insert():
    """Attacker inserts receipt with past timestamp."""
    print("=== Scenario 2: Retroactive Insert ===")
    now = time.time()
    
    chain = []
    prev = "genesis"
    for i in range(3):
        t = now - 300 + i * 60
        r = Receipt(f"r{i:03d}", "kit_fox", t, prev, f"content_{i}",
                    [make_witness("w1", t + 1), make_witness("w2", t + 2)])
        prev = r.receipt_hash
        chain.append(r)
    
    # Attacker inserts receipt claiming earlier time
    injected = Receipt("r_injected", "attacker", now - 400, prev, "malicious_content",
                       [make_witness("w_fake", now - 400)])
    chain.append(injected)
    
    result = audit_chain(chain)
    print(f"  Verdict: {result['verdict']} (Grade {result['grade']})")
    print(f"  Types: {result['injection_types_detected']}")
    for a in result['alerts']:
        print(f"    {a['type']}: {a['severity']} @ {a['receipt']}")
    print()


def scenario_witness_disagreement():
    """Witnesses give conflicting timestamps (clock manipulation)."""
    print("=== Scenario 3: Witness Disagreement ===")
    now = time.time()
    
    r = Receipt("r_disputed", "suspicious_agent", now, "genesis", "content",
                [make_witness("w1", now), make_witness("w2", now + 60),
                 make_witness("w3", now - 45)])
    
    result = audit_chain([r])
    print(f"  Verdict: {result['verdict']} (Grade {result['grade']})")
    for a in result['alerts']:
        print(f"    {a['type']}: skew={a['evidence'].get('max_skew_seconds', 'n/a')}s")
    print()


def scenario_hash_chain_break():
    """Receipt references wrong predecessor (insertion/deletion)."""
    print("=== Scenario 4: Hash Chain Break ===")
    now = time.time()
    
    r0 = Receipt("r000", "kit_fox", now - 200, "genesis", "c0",
                 [make_witness("w1", now - 199), make_witness("w2", now - 198)])
    r1 = Receipt("r001", "kit_fox", now - 100, r0.receipt_hash, "c1",
                 [make_witness("w1", now - 99), make_witness("w2", now - 98)])
    # r2 references wrong prev_hash (as if r1 was deleted/replaced)
    r2 = Receipt("r002", "kit_fox", now, "wrong_hash_here", "c2",
                 [make_witness("w1", now + 1), make_witness("w2", now + 2)])
    
    result = audit_chain([r0, r1, r2])
    print(f"  Verdict: {result['verdict']} (Grade {result['grade']})")
    for a in result['alerts']:
        print(f"    {a['type']}: {a['severity']} @ {a['receipt']}")
    print()


def scenario_future_timestamp():
    """Receipt claims future time (pre-dated injection)."""
    print("=== Scenario 5: Future Timestamp ===")
    now = time.time()
    
    r = Receipt("r_future", "time_traveler", now + 7200, "genesis", "future_content",
                [make_witness("w1", now + 7201), make_witness("w2", now + 7202)])
    
    result = audit_chain([r])
    print(f"  Verdict: {result['verdict']} (Grade {result['grade']})")
    for a in result['alerts']:
        print(f"    {a['type']}: future_offset={a['evidence'].get('future_offset_seconds', 'n/a')}s")
    print()


if __name__ == "__main__":
    print("Write-Time Injection Detector — Temporal Integrity for ATF Chains")
    print("Per skinner + Lamport (1978)")
    print("=" * 65)
    print()
    scenario_clean_chain()
    scenario_retroactive_insert()
    scenario_witness_disagreement()
    scenario_hash_chain_break()
    scenario_future_timestamp()
    print("=" * 65)
    print("KEY: K-of-N temporal witnesses + hash chains + causal ordering")
    print("= three independent detection axes for write-time injection.")
    print("Single witness = vulnerability. Composition = clinical defense.")
