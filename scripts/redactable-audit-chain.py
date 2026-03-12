#!/usr/bin/env python3
"""
redactable-audit-chain.py — Audit log with authorized redaction.

Based on:
- Ateniese et al 2005: Chameleon hash for redactable signatures
- Derler et al NDSS 2019: Fine-grained rewriting in blockchains
- GDPR Art 17 vs audit trail mandates: the erasure paradox

Key insight: append-only for integrity, but authorized redaction
without breaking the hash chain. Hash the FACT of deletion,
not the deleted content.

Usage: python3 redactable-audit-chain.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AuditEntry:
    index: int
    action: str
    scope_hash: str
    content: str
    timestamp: float
    prev_hash: str
    redacted: bool = False
    redaction_reason: Optional[str] = None
    redaction_timestamp: Optional[float] = None
    original_content_hash: Optional[str] = None  # proves content existed

    def compute_hash(self) -> str:
        """Hash includes redaction metadata — chain integrity survives redaction."""
        data = f"{self.index}|{self.action}|{self.scope_hash}|{self.timestamp}|{self.prev_hash}"
        if self.redacted:
            # Hash proves: something was here, it was redacted, and why
            data += f"|REDACTED|{self.original_content_hash}|{self.redaction_reason}"
        else:
            data += f"|{self.content}"
        return hashlib.sha256(data.encode()).hexdigest()


class RedactableAuditChain:
    def __init__(self):
        self.entries: list[AuditEntry] = []
        self.redaction_log: list[dict] = []  # separate log of redaction events

    def append(self, action: str, content: str, scope_hash: str = "default") -> AuditEntry:
        prev_hash = self.entries[-1].compute_hash() if self.entries else "genesis"
        entry = AuditEntry(
            index=len(self.entries),
            action=action,
            scope_hash=scope_hash,
            content=content,
            timestamp=time.time(),
            prev_hash=prev_hash
        )
        self.entries.append(entry)
        return entry

    def redact(self, index: int, reason: str, authority: str) -> dict:
        """Redact entry content while preserving chain integrity."""
        if index >= len(self.entries) or index < 0:
            return {"success": False, "error": "invalid index"}

        entry = self.entries[index]
        if entry.redacted:
            return {"success": False, "error": "already redacted"}

        # Preserve proof that content existed
        original_hash = hashlib.sha256(entry.content.encode()).hexdigest()

        # Redact
        entry.original_content_hash = original_hash
        entry.redacted = True
        entry.redaction_reason = reason
        entry.redaction_timestamp = time.time()
        entry.content = "[REDACTED]"

        # Log the redaction event
        redaction_event = {
            "index": index,
            "reason": reason,
            "authority": authority,
            "original_content_hash": original_hash,
            "timestamp": entry.redaction_timestamp
        }
        self.redaction_log.append(redaction_event)

        # Re-chain downstream entries (redaction changes this entry's hash)
        for i in range(index + 1, len(self.entries)):
            self.entries[i].prev_hash = self.entries[i - 1].compute_hash()

        return {"success": True, "original_content_hash": original_hash}

    def verify_chain(self) -> dict:
        """Verify chain integrity (works even with redactions)."""
        if not self.entries:
            return {"valid": True, "length": 0}

        errors = []
        for i, entry in enumerate(self.entries):
            if i == 0:
                expected_prev = "genesis"
            else:
                expected_prev = self.entries[i - 1].compute_hash()

            if entry.prev_hash != expected_prev:
                errors.append(f"entry {i}: prev_hash mismatch")

        return {
            "valid": len(errors) == 0,
            "length": len(self.entries),
            "redacted_count": sum(1 for e in self.entries if e.redacted),
            "errors": errors
        }

    def audit_report(self) -> dict:
        """Generate compliance report."""
        total = len(self.entries)
        redacted = sum(1 for e in self.entries if e.redacted)
        verification = self.verify_chain()

        # Coverage: what % of the timeline is visible?
        coverage = (total - redacted) / total if total > 0 else 1.0

        # Grade
        if not verification["valid"]:
            grade = "F"
            status = "CHAIN BROKEN — tamper detected"
        elif coverage >= 0.9:
            grade = "A"
            status = "HEALTHY — high visibility"
        elif coverage >= 0.7:
            grade = "B"
            status = "ACCEPTABLE — some redactions"
        elif coverage >= 0.5:
            grade = "C"
            status = "CONCERNING — heavy redaction"
        else:
            grade = "D"
            status = "SUSPICIOUS — majority redacted"

        return {
            "grade": grade,
            "status": status,
            "total_entries": total,
            "redacted": redacted,
            "visible": total - redacted,
            "coverage": f"{coverage:.1%}",
            "chain_valid": verification["valid"],
            "redaction_reasons": [r["reason"] for r in self.redaction_log]
        }


def demo():
    print("=" * 60)
    print("Redactable Audit Chain")
    print("Ateniese 2005 / Derler NDSS 2019 / GDPR Art 17")
    print("=" * 60)

    chain = RedactableAuditChain()

    # Build a realistic audit trail
    events = [
        ("heartbeat", "checked clawk: 3 mentions, replied to santaclawd", "scope_abc"),
        ("attestation", "signed: agent_beta scope_hash=def123", "scope_abc"),
        ("email_send", "sent PII: user@example.com re: tc4 brief", "scope_abc"),
        ("heartbeat", "checked moltbook: no new posts", "scope_abc"),
        ("build", "committed threshold-key-custody.py", "scope_abc"),
        ("dm_received", "private message from human user: personal data", "scope_abc"),
        ("heartbeat", "clawk reply to gendolf re: bridge security", "scope_abc"),
    ]

    for action, content, scope in events:
        chain.append(action, content, scope)

    print(f"\n{'─' * 50}")
    print("Initial chain:")
    v = chain.verify_chain()
    print(f"  Entries: {v['length']}, Valid: {v['valid']}")

    # GDPR erasure request — redact PII entries
    print(f"\n{'─' * 50}")
    print("GDPR Art 17 erasure request received...")

    r1 = chain.redact(2, "GDPR Art 17 erasure request", "data_controller")
    print(f"  Redacted entry 2 (email with PII): {r1['success']}")
    print(f"  Original content hash preserved: {r1['original_content_hash'][:16]}...")

    r2 = chain.redact(5, "GDPR Art 17 erasure request", "data_controller")
    print(f"  Redacted entry 5 (private DM): {r2['success']}")

    # Verify chain still valid after redaction
    print(f"\n{'─' * 50}")
    print("Post-redaction verification:")
    v2 = chain.verify_chain()
    print(f"  Chain valid: {v2['valid']}")
    print(f"  Total: {v2['length']}, Redacted: {v2['redacted_count']}")

    # Show what auditor sees
    print(f"\n{'─' * 50}")
    print("Auditor's view:")
    for entry in chain.entries:
        status = "🔴 REDACTED" if entry.redacted else "🟢"
        print(f"  [{entry.index}] {status} {entry.action}: {entry.content[:50]}")
        if entry.redacted:
            print(f"       Reason: {entry.redaction_reason}")
            print(f"       Proof of existence: {entry.original_content_hash[:16]}...")

    # Audit report
    print(f"\n{'─' * 50}")
    report = chain.audit_report()
    print(f"Audit Report:")
    print(f"  Grade: {report['grade']} — {report['status']}")
    print(f"  Coverage: {report['coverage']}")
    print(f"  Chain integrity: {'✓' if report['chain_valid'] else '✗'}")

    # Tamper detection demo
    print(f"\n{'─' * 50}")
    print("Tamper attempt: modify entry 3 content...")
    chain.entries[3].content = "TAMPERED: false data injected"
    v3 = chain.verify_chain()
    print(f"  Chain valid after tamper: {v3['valid']}")
    if v3['errors']:
        print(f"  Errors: {v3['errors']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("1. Redaction preserves chain integrity (hash includes redaction metadata)")
    print("2. Original content hash proves something WAS there")
    print("3. Redaction reason is itself auditable")
    print("4. Tampering detected even on non-redacted entries")
    print("5. GDPR compliance + audit integrity = not contradictory")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
