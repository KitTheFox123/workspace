#!/usr/bin/env python3
"""
trace-custody-spec.py — Trace custody for execution trace commitment.

Based on:
- santaclawd: "who holds the trace? agent offline = hash unverifiable = dispute deadlock"
- Ethereum data availability: erasure coding + DAS (Al-Bassam et al 2018)
- Two-phase commit: trace escrow at commit time, not settlement

The problem: execution_trace_hash at settlement proves trace EXISTED.
But if trace holder is offline during dispute, hash is unverifiable.
Hash without data = unauditable. Same as delivery_hash without delivery.

Three custody tiers:
1. Counterparty escrow (email trace at scoring time) — cheapest
2. CID on IPFS — distributed, available while pinned
3. On-chain commitment — immutable, expensive
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CustodyTier(Enum):
    SELF = "self_custody"           # Scorer holds trace (fragile)
    COUNTERPARTY = "counterparty"   # Email to counterparty (SMTP)
    IPFS = "ipfs_cid"              # CID on IPFS (available while pinned)
    ESCROW = "third_party_escrow"   # Neutral escrow service
    ONCHAIN = "on_chain"           # Immutable (expensive)


@dataclass
class TraceCustodyRecord:
    trace_hash: str
    custody_tier: CustodyTier
    custodians: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    availability_proof: Optional[str] = None  # CID, tx_hash, message_id
    expiry: Optional[float] = None


@dataclass
class DisputeResolution:
    trace_available: bool
    custody_tier: CustodyTier
    resolution_time_hours: float
    grade: str
    diagnosis: str


def hash_trace(trace_data: dict) -> str:
    return hashlib.sha256(json.dumps(trace_data, sort_keys=True).encode()).hexdigest()[:16]


def evaluate_custody(record: TraceCustodyRecord, dispute_time: float) -> DisputeResolution:
    """Evaluate custody during dispute."""
    # Is trace still available?
    if record.expiry and dispute_time > record.expiry:
        return DisputeResolution(False, record.custody_tier, 0,
                                  "F", "TRACE_EXPIRED")

    tier = record.custody_tier

    if tier == CustodyTier.SELF:
        # Agent offline = deadlock
        return DisputeResolution(False, tier, float('inf'),
                                  "F", "DISPUTE_DEADLOCK")

    elif tier == CustodyTier.COUNTERPARTY:
        # Counterparty has copy via SMTP
        return DisputeResolution(True, tier, 2.0,
                                  "B", "SMTP_CUSTODY")

    elif tier == CustodyTier.IPFS:
        # Available if pinned
        if record.availability_proof:
            return DisputeResolution(True, tier, 0.5,
                                      "A", "CID_AVAILABLE")
        return DisputeResolution(False, tier, 0,
                                  "D", "CID_UNPINNED")

    elif tier == CustodyTier.ESCROW:
        return DisputeResolution(True, tier, 1.0,
                                  "A", "ESCROW_AVAILABLE")

    elif tier == CustodyTier.ONCHAIN:
        return DisputeResolution(True, tier, 0.1,
                                  "A", "ONCHAIN_IMMUTABLE")

    return DisputeResolution(False, tier, 0, "F", "UNKNOWN")


def cost_analysis() -> list[dict]:
    """Cost per trace custody tier."""
    return [
        {"tier": "self", "cost_usd": 0.0, "availability": "fragile",
         "dispute_resolution": "deadlock if offline", "grade": "F"},
        {"tier": "smtp_counterparty", "cost_usd": 0.0, "availability": "counterparty uptime",
         "dispute_resolution": "2hr (email retrieval)", "grade": "B"},
        {"tier": "ipfs_pinned", "cost_usd": 0.01, "availability": "while pinned",
         "dispute_resolution": "30min (CID fetch)", "grade": "A"},
        {"tier": "third_party_escrow", "cost_usd": 0.05, "availability": "SLA-bound",
         "dispute_resolution": "1hr (escrow query)", "grade": "A"},
        {"tier": "on_chain", "cost_usd": 0.50, "availability": "permanent",
         "dispute_resolution": "6min (block confirmation)", "grade": "A"},
    ]


def main():
    print("=" * 70)
    print("TRACE CUSTODY SPECIFICATION")
    print("santaclawd: 'who holds the trace? offline = unverifiable = deadlock'")
    print("=" * 70)

    # Simulate dispute scenarios
    now = time.time()
    scenarios = [
        ("self_custody_offline", TraceCustodyRecord(
            hash_trace({"rule": "brier", "score": 0.92}),
            CustodyTier.SELF, ["scoring_agent"], now - 3600)),
        ("smtp_counterparty", TraceCustodyRecord(
            hash_trace({"rule": "brier", "score": 0.92}),
            CustodyTier.COUNTERPARTY, ["buyer", "seller"], now - 3600,
            "msg_id_12345")),
        ("ipfs_pinned", TraceCustodyRecord(
            hash_trace({"rule": "brier", "score": 0.92}),
            CustodyTier.IPFS, ["ipfs_gateway"], now - 3600,
            "QmXyz123...")),
        ("ipfs_unpinned", TraceCustodyRecord(
            hash_trace({"rule": "brier", "score": 0.92}),
            CustodyTier.IPFS, ["ipfs_gateway"], now - 3600)),
        ("escrow_service", TraceCustodyRecord(
            hash_trace({"rule": "brier", "score": 0.92}),
            CustodyTier.ESCROW, ["isnad_escrow"], now - 3600,
            "escrow_receipt_abc")),
    ]

    print(f"\n{'Scenario':<25} {'Grade':<6} {'Available':<10} {'Hours':<8} {'Diagnosis'}")
    print("-" * 70)

    for name, record in scenarios:
        result = evaluate_custody(record, now)
        hrs = f"{result.resolution_time_hours:.1f}" if result.resolution_time_hours < 1000 else "∞"
        print(f"{name:<25} {result.grade:<6} {str(result.trace_available):<10} {hrs:<8} {result.diagnosis}")

    # Cost analysis
    print(f"\n--- Cost Analysis ---")
    print(f"{'Tier':<22} {'Cost':<10} {'Availability':<22} {'Resolution'}")
    print("-" * 70)
    for c in cost_analysis():
        print(f"{c['tier']:<22} ${c['cost_usd']:<9.2f} {c['availability']:<22} {c['dispute_resolution']}")

    # Two-phase trace custody protocol
    print("\n--- Two-Phase Trace Custody Protocol ---")
    print("Phase 1 (at scoring time):")
    print("  1. Score the delivery")
    print("  2. Generate execution trace")
    print("  3. Hash trace → execution_trace_hash")
    print("  4. ESCROW trace: email to counterparty + CID to IPFS")
    print("  5. Commit: {delivery_hash, score, execution_trace_hash, escrow_proof}")
    print()
    print("Phase 2 (at dispute time):")
    print("  1. Challenger requests trace by execution_trace_hash")
    print("  2. Fetch from escrow (counterparty email OR IPFS CID)")
    print("  3. Verify: hash(fetched_trace) == committed_hash")
    print("  4. Replay trace to verify scoring process")
    print()
    print("Key: trace escrow at COMMIT time, not settlement time.")
    print("SMTP = trace custody at zero cost. CID = backup.")
    print("Hash without data = unauditable. Data without hash = untrusted.")


if __name__ == "__main__":
    main()
