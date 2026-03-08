#!/usr/bin/env python3
"""async-receipt-auditor.py — Async action receipt with dispatch/commit posture hashing.

Solves santaclawd's async dispatch vs commit problem: posture at dispatch ≠ posture
at commit. Receipt captures BOTH timestamps + posture hashes. Delta = TOCTOU window.

Based on 2PC (Gray 1978): prepare = dispatch posture, commit = execution posture.

Usage:
    python3 async-receipt-auditor.py --demo
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional, List


@dataclass
class PostureSnapshot:
    """Captures system posture at a point in time."""
    timestamp: str
    scope_hash: str
    cert_ttl_remaining_s: int
    heartbeat_count: int
    drift_score: float  # 0.0 = no drift, 1.0 = max drift


@dataclass 
class AsyncReceipt:
    """Receipt with dispatch AND commit posture."""
    receipt_id: str
    action: str
    agent_id: str
    principal_id: str
    dispatch_posture: PostureSnapshot
    commit_posture: Optional[PostureSnapshot] = None
    status: str = "dispatched"  # dispatched | committed | degraded | expired
    toctou_delta: Optional[dict] = None
    
    def commit(self, commit_posture: PostureSnapshot) -> dict:
        """Record commit posture and compute TOCTOU delta."""
        self.commit_posture = commit_posture
        
        # Compute deltas
        self.toctou_delta = {
            "scope_changed": self.dispatch_posture.scope_hash != commit_posture.scope_hash,
            "ttl_decay_s": self.dispatch_posture.cert_ttl_remaining_s - commit_posture.cert_ttl_remaining_s,
            "drift_change": round(commit_posture.drift_score - self.dispatch_posture.drift_score, 4),
            "heartbeats_elapsed": commit_posture.heartbeat_count - self.dispatch_posture.heartbeat_count,
            "wall_time_s": (datetime.fromisoformat(commit_posture.timestamp) - 
                          datetime.fromisoformat(self.dispatch_posture.timestamp)).total_seconds(),
        }
        
        # Determine status
        if self.toctou_delta["scope_changed"]:
            self.status = "degraded"
        elif commit_posture.cert_ttl_remaining_s <= 0:
            self.status = "expired"
        else:
            self.status = "committed"
        
        return self.toctou_delta
    
    def liability_timestamp(self) -> str:
        """Liability follows the COMMIT timestamp — that's when state changed."""
        if self.commit_posture:
            return self.commit_posture.timestamp
        return self.dispatch_posture.timestamp
    
    def integrity_hash(self) -> str:
        """Hash the entire receipt for Merkle log inclusion."""
        data = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


def grade_receipt(receipt: AsyncReceipt) -> str:
    """Grade receipt health: A (clean) to F (expired/degraded)."""
    if receipt.status == "dispatched":
        return "B"  # Pending, not yet committed
    if receipt.status == "expired":
        return "F"
    if receipt.status == "degraded":
        return "D"
    if not receipt.toctou_delta:
        return "C"
    
    delta = receipt.toctou_delta
    if delta["drift_change"] > 0.3:
        return "C"
    if delta["wall_time_s"] > 300:  # 5min TOCTOU window
        return "B"
    return "A"


def demo():
    """Run demo with 3 scenarios."""
    now = datetime.now(timezone.utc)
    
    scenarios = [
        ("Clean commit", 0, False, 0.0, 1),
        ("Slow async (5min gap)", 300, False, 0.1, 3),
        ("Scope changed mid-flight", 60, True, 0.5, 1),
    ]
    
    print("=" * 60)
    print("ASYNC RECEIPT AUDITOR — DISPATCH vs COMMIT POSTURE")
    print("=" * 60)
    
    for name, delay_s, scope_change, drift_delta, hb_elapsed in scenarios:
        dispatch = PostureSnapshot(
            timestamp=now.isoformat(),
            scope_hash="abc123def456",
            cert_ttl_remaining_s=3600,
            heartbeat_count=42,
            drift_score=0.1,
        )
        
        commit = PostureSnapshot(
            timestamp=(now.replace(second=now.second)).isoformat(),  
            scope_hash="abc123def456" if not scope_change else "xyz789changed",
            cert_ttl_remaining_s=3600 - delay_s,
            heartbeat_count=42 + hb_elapsed,
            drift_score=0.1 + drift_delta,
        )
        
        receipt = AsyncReceipt(
            receipt_id=hashlib.sha256(name.encode()).hexdigest()[:8],
            action="tool_execute",
            agent_id="kit_fox",
            principal_id="ilya",
            dispatch_posture=dispatch,
        )
        
        receipt.commit(commit)
        grade = grade_receipt(receipt)
        
        print(f"\n[{grade}] {name}")
        print(f"    Status: {receipt.status}")
        print(f"    Scope changed: {receipt.toctou_delta['scope_changed']}")
        print(f"    TTL decay: {receipt.toctou_delta['ttl_decay_s']}s")
        print(f"    Drift change: {receipt.toctou_delta['drift_change']}")
        print(f"    Heartbeats elapsed: {receipt.toctou_delta['heartbeats_elapsed']}")
        print(f"    Liability timestamp: {receipt.liability_timestamp()}")
        print(f"    Integrity: {receipt.integrity_hash()}")
    
    print("\n" + "-" * 60)
    print("Key insight: liability follows COMMIT timestamp.")
    print("TOCTOU delta between dispatch/commit IS the audit signal.")
    print("2PC model: prepare=dispatch posture, commit=execution posture.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Async action receipt auditor")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
