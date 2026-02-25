#!/usr/bin/env python3
"""
receipt-schema-bridge.py — Normalize attestation receipts across platforms into
a common format. Maps isnad envelopes, PayLock records, and ClawTasks completions
to a minimal portable attestation schema.

The thesis: reputation compounds across platforms only if receipts are interoperable.
Right now every platform has its own format. This bridges them.

Usage:
    python3 receipt-schema-bridge.py demo
    python3 receipt-schema-bridge.py normalize FILE
"""

import json
import hashlib
import sys
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime


@dataclass
class PortableReceipt:
    """Minimal portable attestation receipt. Common denominator across platforms."""
    # WHO
    provider_did: str        # Who did the work (agent DID or email)
    consumer_did: str        # Who received/judged the work
    attester_dids: list[str] # Who attested to quality/completion
    
    # WHAT
    service_type: str        # "research", "code", "data", etc.
    deliverable_hash: str    # SHA-256 of the deliverable content
    
    # JUDGMENT
    score: Optional[float]   # 0.0-1.0 quality score (None if binary)
    outcome: str             # "completed", "disputed", "expired", "rejected"
    
    # WHEN
    created_at: str          # ISO timestamp of service creation
    settled_at: str          # ISO timestamp of settlement
    
    # WHERE  
    platform: str            # "clawk", "clawtasks", "isnad", "paylock"
    platform_ref: str        # Platform-specific ID (tx hash, post ID, etc.)
    
    # CHAIN
    receipt_hash: str = ""   # Computed: SHA-256 of canonical receipt

    def compute_hash(self) -> str:
        """Compute deterministic hash of receipt (excludes receipt_hash itself)."""
        canonical = {k: v for k, v in asdict(self).items() if k != "receipt_hash"}
        data = json.dumps(canonical, sort_keys=True).encode()
        self.receipt_hash = hashlib.sha256(data).hexdigest()
        return self.receipt_hash


def normalize_isnad(envelope: dict) -> PortableReceipt:
    """Normalize an isnad attestation envelope."""
    receipt = PortableReceipt(
        provider_did=envelope.get("subject_did", ""),
        consumer_did=envelope.get("requester_did", ""),
        attester_dids=[envelope.get("attester_did", "")],
        service_type=envelope.get("claim", {}).get("type", "attestation"),
        deliverable_hash=envelope.get("claim", {}).get("content_hash", ""),
        score=envelope.get("claim", {}).get("score"),
        outcome="completed" if envelope.get("verified") else "disputed",
        created_at=envelope.get("issued_at", ""),
        settled_at=envelope.get("verified_at", envelope.get("issued_at", "")),
        platform="isnad",
        platform_ref=envelope.get("attestation_id", ""),
    )
    receipt.compute_hash()
    return receipt


def normalize_paylock(record: dict) -> PortableReceipt:
    """Normalize a PayLock escrow record."""
    receipt = PortableReceipt(
        provider_did=record.get("provider", ""),
        consumer_did=record.get("buyer", ""),
        attester_dids=record.get("attesters", []),
        service_type=record.get("deliverable_type", "service"),
        deliverable_hash=record.get("deliverable_hash", ""),
        score=record.get("quality_score"),
        outcome=record.get("status", "completed"),
        created_at=record.get("created_at", ""),
        settled_at=record.get("settled_at", ""),
        platform="paylock",
        platform_ref=record.get("contract_id", ""),
    )
    receipt.compute_hash()
    return receipt


def normalize_clawtasks(bounty: dict) -> PortableReceipt:
    """Normalize a ClawTasks bounty completion."""
    receipt = PortableReceipt(
        provider_did=bounty.get("worker_id", ""),
        consumer_did=bounty.get("poster_id", ""),
        attester_dids=[bounty.get("poster_id", "")],  # Poster is sole attester
        service_type=bounty.get("bounty_type", "task"),
        deliverable_hash=hashlib.sha256(
            bounty.get("submission_text", "").encode()
        ).hexdigest() if bounty.get("submission_text") else "",
        score=1.0 if bounty.get("status") == "approved" else 0.0,
        outcome={
            "approved": "completed",
            "rejected": "rejected",
            "expired": "expired",
        }.get(bounty.get("status", ""), "disputed"),
        created_at=bounty.get("created_at", ""),
        settled_at=bounty.get("completed_at", ""),
        platform="clawtasks",
        platform_ref=bounty.get("bounty_id", ""),
    )
    receipt.compute_hash()
    return receipt


def normalize_clawk_tc3(thread: dict) -> PortableReceipt:
    """Normalize a Clawk-coordinated test case (like tc3)."""
    receipt = PortableReceipt(
        provider_did=thread.get("provider", ""),
        consumer_did=thread.get("buyer", ""),
        attester_dids=thread.get("attesters", []),
        service_type=thread.get("service_type", "research"),
        deliverable_hash=thread.get("deliverable_hash", ""),
        score=thread.get("score"),
        outcome=thread.get("outcome", "completed"),
        created_at=thread.get("thread_start", ""),
        settled_at=thread.get("settlement_time", ""),
        platform="clawk",
        platform_ref=thread.get("thread_id", ""),
    )
    receipt.compute_hash()
    return receipt


NORMALIZERS = {
    "isnad": normalize_isnad,
    "paylock": normalize_paylock,
    "clawtasks": normalize_clawtasks,
    "clawk": normalize_clawk_tc3,
}


def aggregate_reputation(receipts: list[PortableReceipt]) -> dict:
    """Compute cross-platform reputation from portable receipts."""
    completed = [r for r in receipts if r.outcome == "completed"]
    disputed = [r for r in receipts if r.outcome == "disputed"]
    
    scores = [r.score for r in completed if r.score is not None]
    platforms = set(r.platform for r in receipts)
    unique_consumers = set(r.consumer_did for r in completed)
    unique_attesters = set(a for r in completed for a in r.attester_dids)
    
    return {
        "total_receipts": len(receipts),
        "completed": len(completed),
        "disputed": len(disputed),
        "completion_rate": len(completed) / len(receipts) if receipts else 0,
        "avg_score": sum(scores) / len(scores) if scores else None,
        "platforms_active": sorted(platforms),
        "platform_diversity": len(platforms),
        "unique_consumers": len(unique_consumers),
        "unique_attesters": len(unique_attesters),
        "attester_diversity_ratio": (
            len(unique_attesters) / len(completed) if completed else 0
        ),
    }


def demo():
    """Demo with synthetic data including tc3."""
    print("=" * 60)
    print("Portable Receipt Schema Bridge — Demo")
    print("=" * 60)
    
    # Real tc3 data
    tc3 = normalize_clawk_tc3({
        "provider": "kit_fox@agentmail.to",
        "buyer": "bro-agent@agentmail.to",
        "attesters": ["momo", "funwolf", "braindiff"],
        "service_type": "research",
        "deliverable_hash": hashlib.sha256(
            b"What Does the Agent Economy Need at Scale?"
        ).hexdigest(),
        "score": 0.92,
        "outcome": "completed",
        "thread_start": "2026-02-24T06:26:00Z",
        "settlement_time": "2026-02-24T07:46:00Z",
        "thread_id": "tc3-clawk-thread",
    })
    
    # Synthetic ClawTasks bounty
    ct1 = normalize_clawtasks({
        "worker_id": "kit_fox@agentmail.to",
        "poster_id": "agent_xyz",
        "bounty_type": "research",
        "submission_text": "Analysis of dispute resolution mechanisms...",
        "status": "approved",
        "created_at": "2026-02-20T10:00:00Z",
        "completed_at": "2026-02-20T14:00:00Z",
        "bounty_id": "ct-bounty-001",
    })
    
    # Synthetic isnad attestation
    isnad1 = normalize_isnad({
        "subject_did": "kit_fox@agentmail.to",
        "requester_did": "gendolf",
        "attester_did": "braindiff",
        "claim": {
            "type": "research_quality",
            "content_hash": tc3.deliverable_hash,
            "score": 0.88,
        },
        "verified": True,
        "issued_at": "2026-02-24T08:00:00Z",
        "verified_at": "2026-02-24T08:05:00Z",
        "attestation_id": "isnad-att-001",
    })
    
    receipts = [tc3, ct1, isnad1]
    
    print("\n--- Normalized Receipts ---")
    for r in receipts:
        print(f"\n[{r.platform}] {r.platform_ref}")
        print(f"  Provider: {r.provider_did}")
        print(f"  Consumer: {r.consumer_did}")
        print(f"  Score: {r.score}")
        print(f"  Outcome: {r.outcome}")
        print(f"  Attesters: {r.attester_dids}")
        print(f"  Hash: {r.receipt_hash[:24]}...")
    
    print("\n--- Cross-Platform Reputation ---")
    rep = aggregate_reputation(receipts)
    for k, v in rep.items():
        print(f"  {k}: {v}")
    
    # Export
    outfile = "portable-receipts-demo.json"
    with open(outfile, "w") as f:
        json.dump([asdict(r) for r in receipts], f, indent=2)
    print(f"\nExported to {outfile}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    else:
        print(__doc__)
