#!/usr/bin/env python3
"""async-receipt-validator.py — Two-phase action receipt validator.

Models the dispatch-commit gap in async agent workflows (Gray 1978 2PC).
Captures posture_hash at dispatch AND commit, flags divergence.

Receipt schema:
  - cert_id: scope certificate in effect
  - dispatched_at: when action was authorized
  - committed_at: when action completed
  - posture_hash_dispatch: behavioral state at authorization
  - posture_hash_commit: behavioral state at completion
  - action_hash: what was actually done
  - delta_seconds: commit - dispatch gap

Flags:
  - POSTURE_DRIFT: posture changed between dispatch and commit
  - TTL_EXCEEDED: action committed after cert expired
  - ASYNC_GAP: dispatch-commit delta exceeds threshold

Usage:
    python3 async-receipt-validator.py --demo
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class ActionReceipt:
    """Two-phase action receipt."""
    receipt_id: str
    cert_id: str
    agent_id: str
    action_description: str
    dispatched_at: float  # unix timestamp
    committed_at: Optional[float] = None
    posture_hash_dispatch: str = ""
    posture_hash_commit: str = ""
    action_hash: str = ""
    cert_ttl_seconds: int = 3600
    
    @property
    def delta_seconds(self) -> Optional[float]:
        if self.committed_at:
            return self.committed_at - self.dispatched_at
        return None
    
    @property
    def posture_drifted(self) -> bool:
        return (self.posture_hash_dispatch != self.posture_hash_commit 
                and self.posture_hash_commit != "")
    
    @property
    def ttl_exceeded(self) -> bool:
        if self.committed_at:
            return (self.committed_at - self.dispatched_at) > self.cert_ttl_seconds
        return False


@dataclass 
class ValidationResult:
    """Result of receipt validation."""
    receipt_id: str
    flags: List[str]
    severity: str  # OK, WARN, CRITICAL
    delta_seconds: Optional[float]
    posture_drifted: bool
    ttl_exceeded: bool
    recommendation: str


def hash_posture(state: dict) -> str:
    """Hash a posture snapshot."""
    canonical = json.dumps(state, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def validate_receipt(receipt: ActionReceipt, max_async_gap: float = 300) -> ValidationResult:
    """Validate a two-phase action receipt."""
    flags = []
    
    if receipt.posture_drifted:
        flags.append("POSTURE_DRIFT")
    
    if receipt.ttl_exceeded:
        flags.append("TTL_EXCEEDED")
    
    delta = receipt.delta_seconds
    if delta and delta > max_async_gap:
        flags.append("ASYNC_GAP")
    
    if not receipt.committed_at:
        flags.append("UNCOMMITTED")
    
    # Severity
    if "TTL_EXCEEDED" in flags:
        severity = "CRITICAL"
        rec = "Action committed after cert expired. Reject and re-authorize."
    elif "POSTURE_DRIFT" in flags and "ASYNC_GAP" in flags:
        severity = "CRITICAL" 
        rec = "Posture changed during long async gap. Possible compromise during execution."
    elif "POSTURE_DRIFT" in flags:
        severity = "WARN"
        rec = "Posture changed between dispatch and commit. Review action outcome."
    elif "ASYNC_GAP" in flags:
        severity = "WARN"
        rec = f"Dispatch-commit gap ({delta:.0f}s) exceeds threshold ({max_async_gap}s)."
    elif "UNCOMMITTED" in flags:
        severity = "WARN"
        rec = "Action dispatched but not committed. Check for stuck execution."
    else:
        severity = "OK"
        rec = "Receipt valid. Posture stable across dispatch-commit."
    
    return ValidationResult(
        receipt_id=receipt.receipt_id,
        flags=flags,
        severity=severity,
        delta_seconds=delta,
        posture_drifted=receipt.posture_drifted,
        ttl_exceeded=receipt.ttl_exceeded,
        recommendation=rec,
    )


def demo():
    """Demo with realistic scenarios."""
    now = time.time()
    
    posture_healthy = {"scope_lines": 8, "tools_loaded": 5, "cert_valid": True}
    posture_drifted = {"scope_lines": 12, "tools_loaded": 7, "cert_valid": True}
    posture_expired = {"scope_lines": 8, "tools_loaded": 5, "cert_valid": False}
    
    scenarios = [
        ActionReceipt(
            receipt_id="r001", cert_id="cert-a1", agent_id="kit",
            action_description="Search Keenable for trust research",
            dispatched_at=now - 30, committed_at=now,
            posture_hash_dispatch=hash_posture(posture_healthy),
            posture_hash_commit=hash_posture(posture_healthy),
            action_hash="act-001",
        ),
        ActionReceipt(
            receipt_id="r002", cert_id="cert-a1", agent_id="kit",
            action_description="Post to Moltbook with research",
            dispatched_at=now - 120, committed_at=now,
            posture_hash_dispatch=hash_posture(posture_healthy),
            posture_hash_commit=hash_posture(posture_drifted),
            action_hash="act-002",
        ),
        ActionReceipt(
            receipt_id="r003", cert_id="cert-a1", agent_id="kit",
            action_description="Long-running data analysis",
            dispatched_at=now - 600, committed_at=now,
            posture_hash_dispatch=hash_posture(posture_healthy),
            posture_hash_commit=hash_posture(posture_healthy),
            action_hash="act-003",
        ),
        ActionReceipt(
            receipt_id="r004", cert_id="cert-a1", agent_id="kit",
            action_description="Async email send + wait for reply",
            dispatched_at=now - 4000, committed_at=now,
            posture_hash_dispatch=hash_posture(posture_healthy),
            posture_hash_commit=hash_posture(posture_expired),
            action_hash="act-004",
            cert_ttl_seconds=3600,
        ),
        ActionReceipt(
            receipt_id="r005", cert_id="cert-a1", agent_id="kit",
            action_description="Stuck webhook callback",
            dispatched_at=now - 900,
            posture_hash_dispatch=hash_posture(posture_healthy),
            action_hash="act-005",
        ),
    ]
    
    print("=" * 60)
    print("ASYNC ACTION RECEIPT VALIDATION (2PC Model)")
    print("=" * 60)
    print()
    
    for receipt in scenarios:
        result = validate_receipt(receipt)
        icon = {"OK": "✅", "WARN": "⚠️", "CRITICAL": "🔴"}.get(result.severity, "?")
        print(f"{icon} [{result.severity}] {receipt.action_description}")
        if result.delta_seconds:
            print(f"   Delta: {result.delta_seconds:.0f}s")
        if result.flags:
            print(f"   Flags: {', '.join(result.flags)}")
        print(f"   → {result.recommendation}")
        print()
    
    # Summary
    results = [validate_receipt(r) for r in scenarios]
    ok = sum(1 for r in results if r.severity == "OK")
    warn = sum(1 for r in results if r.severity == "WARN")
    crit = sum(1 for r in results if r.severity == "CRITICAL")
    print(f"Summary: {ok} OK, {warn} WARN, {crit} CRITICAL")
    print(f"Key insight: posture_hash at BOTH dispatch and commit closes the TOCTOU gap.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Two-phase action receipt validator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
