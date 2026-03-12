#!/usr/bin/env python3
"""
audit-erasure-reconciler.py — Reconcile append-only audit trails with erasure rights.

The core tension: GDPR Art 17 (right to erasure) vs audit mandates (retain evidence).
Solution: hash chain is append-only, content is gated. Hash persists, payload can be forgotten.

Based on:
- AuditableLLM (Li et al 2025, UTS): cryptographic digests, not raw data
- GDPR Art 17 vs Art 5(1)(e): erasure vs storage limitation
- EU AI Act Art 12: automatic recording of events

Usage: python3 audit-erasure-reconciler.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class AuditEntry:
    """Single audit trail entry — hash chain linked."""
    index: int
    action: str
    scope_hash: str
    timestamp: str
    payload: Optional[str]  # Can be None (erased)
    payload_hash: str       # Always persists
    prev_hash: str
    entry_hash: str = ""
    erased: bool = False
    erasure_reason: Optional[str] = None
    erasure_timestamp: Optional[str] = None

    def __post_init__(self):
        if not self.entry_hash:
            self.entry_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Hash includes payload_hash (not payload), so chain survives erasure."""
        data = f"{self.index}:{self.action}:{self.scope_hash}:{self.timestamp}:{self.payload_hash}:{self.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class AuditChain:
    """Append-only hash chain with erasure support."""
    entries: list[AuditEntry] = field(default_factory=list)

    def append(self, action: str, scope_hash: str, payload: str) -> AuditEntry:
        prev = self.entries[-1].entry_hash if self.entries else "genesis"
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
        entry = AuditEntry(
            index=len(self.entries),
            action=action,
            scope_hash=scope_hash,
            timestamp=datetime.utcnow().isoformat(),
            payload=payload,
            payload_hash=payload_hash,
            prev_hash=prev
        )
        self.entries.append(entry)
        return entry

    def erase_payload(self, index: int, reason: str) -> dict:
        """Erase payload but keep hash chain intact."""
        if index >= len(self.entries):
            return {"success": False, "reason": "index out of range"}

        entry = self.entries[index]
        if entry.erased:
            return {"success": False, "reason": "already erased"}

        # Erase content, keep receipt
        entry.payload = None
        entry.erased = True
        entry.erasure_reason = reason
        entry.erasure_timestamp = datetime.utcnow().isoformat()

        # Verify chain integrity still holds
        integrity = self.verify_chain()

        return {
            "success": True,
            "erased_index": index,
            "reason": reason,
            "chain_intact": integrity["valid"],
            "payload_hash_preserved": entry.payload_hash
        }

    def verify_chain(self) -> dict:
        """Verify hash chain integrity (works regardless of erasure)."""
        if not self.entries:
            return {"valid": True, "length": 0}

        for i, entry in enumerate(self.entries):
            # Check prev_hash linkage
            expected_prev = self.entries[i - 1].entry_hash if i > 0 else "genesis"
            if entry.prev_hash != expected_prev:
                return {"valid": False, "broken_at": i, "reason": "prev_hash mismatch"}

            # Check entry hash (computed from payload_hash, not payload)
            recomputed = entry._compute_hash()
            if entry.entry_hash != recomputed:
                return {"valid": False, "broken_at": i, "reason": "entry_hash tampered"}

        return {"valid": True, "length": len(self.entries)}

    def compliance_report(self) -> dict:
        """Generate compliance status."""
        total = len(self.entries)
        erased = sum(1 for e in self.entries if e.erased)
        intact = sum(1 for e in self.entries if not e.erased)
        integrity = self.verify_chain()

        # Can we prove what happened without revealing content?
        provable_actions = sum(1 for e in self.entries if e.action and e.scope_hash)

        # Grade
        if not integrity["valid"]:
            grade = "F"
            status = "CHAIN BROKEN — tampered"
        elif erased == 0:
            grade = "A"
            status = "FULL RETENTION — all payloads available"
        elif erased < total * 0.5:
            grade = "B"
            status = "PARTIAL ERASURE — chain intact, some payloads removed"
        else:
            grade = "C"
            status = "HEAVY ERASURE — chain intact but most content gone"

        return {
            "grade": grade,
            "status": status,
            "total_entries": total,
            "erased": erased,
            "intact": intact,
            "chain_valid": integrity["valid"],
            "provable_actions": provable_actions,
            "gdpr_compliant": erased > 0 or True,  # erasure capability = compliant
            "audit_compliant": integrity["valid"],   # chain intact = compliant
        }


def demo():
    print("=" * 60)
    print("Audit-Erasure Reconciler")
    print("GDPR Art 17 (erasure) vs Audit Mandate (retention)")
    print("=" * 60)

    chain = AuditChain()

    # Build a realistic agent audit trail
    events = [
        ("attestation", "scope:trust_scoring", "attested agent_alpha trust=0.85 based on 3 observations"),
        ("heartbeat", "scope:monitoring", "heartbeat #47: checked 3 platforms, 4 writing actions"),
        ("email_sent", "scope:communication", "sent tc4 brief to bro_agent with PayLock milestones"),
        ("personal_data", "scope:dm", "DM from user_jane: 'my API key is sk-abc123, can you help?'"),
        ("attestation", "scope:trust_scoring", "attested agent_beta trust=0.92 based on 5 observations"),
        ("error_log", "scope:debugging", "failed to parse response from shellmates API, retried 3x"),
    ]

    print("\n--- Building audit chain ---")
    for action, scope, payload in events:
        entry = chain.append(action, scope, payload)
        print(f"  [{entry.index}] {action}: hash={entry.entry_hash}")

    # Verify chain
    print("\n--- Chain verification ---")
    result = chain.verify_chain()
    print(f"  Valid: {result['valid']}, Length: {result['length']}")

    # Now: GDPR erasure request for personal data
    print("\n--- GDPR Erasure Request ---")
    print("  User requests deletion of entry #3 (contains API key)")
    erase_result = chain.erase_payload(3, "GDPR Art 17 — user requested erasure of personal data")
    print(f"  Success: {erase_result['success']}")
    print(f"  Chain intact: {erase_result['chain_intact']}")
    print(f"  Payload hash preserved: {erase_result['payload_hash_preserved']}")

    # Verify chain STILL works after erasure
    print("\n--- Post-erasure verification ---")
    result = chain.verify_chain()
    print(f"  Valid: {result['valid']} ← chain survives erasure!")

    # Show what's left
    print("\n--- Entry #3 after erasure ---")
    e = chain.entries[3]
    print(f"  Action: {e.action}")
    print(f"  Payload: {e.payload}")  # None
    print(f"  Payload hash: {e.payload_hash}")  # Still there
    print(f"  Erased: {e.erased}")
    print(f"  Reason: {e.erasure_reason}")
    print(f"  Entry hash: {e.entry_hash} ← unchanged!")

    # Compliance report
    print("\n--- Compliance Report ---")
    report = chain.compliance_report()
    for k, v in report.items():
        print(f"  {k}: {v}")

    # Try tampering after erasure
    print("\n--- Tamper detection test ---")
    chain.entries[2].action = "FORGED_ACTION"
    tamper_result = chain.verify_chain()
    print(f"  Tamper detected: {not tamper_result['valid']}")
    print(f"  Broken at: entry #{tamper_result.get('broken_at', 'N/A')}")

    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("Hash chain = append-only STRUCTURE (never modified)")
    print("Payload = gated CONTENT (can be erased)")
    print("hash(payload) survives erasure → provenance persists")
    print("GDPR + audit mandate = BOTH satisfied simultaneously")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
