#!/usr/bin/env python3
"""
redactable-audit-chain.py — Chameleon hash-inspired redactable audit trails.

Based on:
- Krawczyk & Rabin 2000: Chameleon hash functions
- Ateniese et al 2017: Redactable blockchain via chameleon hashing
- funwolf's insight: "hash the FACT of deletion, not the deleted content"

The GDPR vs accountability puzzle: you need to prove you forgot
something without revealing what you forgot. Chameleon hashes let
the trapdoor holder find collisions = redact entries while keeping
the chain valid.

For agent memory pruning: prove deletion happened, preserve chain
integrity, reveal nothing about deleted content.

Usage: python3 redactable-audit-chain.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class AuditEntry:
    index: int
    action: str
    content: str  # actual content or redaction stub
    scope_hash: str
    timestamp: float
    prev_hash: str
    redacted: bool = False
    redaction_proof: Optional[str] = None  # hash proving deletion event
    
    @property
    def entry_hash(self) -> str:
        """Hash of this entry — uses redaction_proof if redacted."""
        if self.redacted:
            # Chain integrity preserved: hash includes proof of deletion
            payload = f"{self.index}|{self.redaction_proof}|{self.scope_hash}|{self.timestamp}|{self.prev_hash}"
        else:
            payload = f"{self.index}|{self.action}|{self.content}|{self.scope_hash}|{self.timestamp}|{self.prev_hash}"
        return sha256(payload)


@dataclass 
class RedactableAuditChain:
    entries: list[AuditEntry] = field(default_factory=list)
    redaction_log: list[dict] = field(default_factory=list)
    
    def append(self, action: str, content: str, scope: str) -> AuditEntry:
        prev = self.entries[-1].entry_hash if self.entries else "genesis"
        entry = AuditEntry(
            index=len(self.entries),
            action=action,
            content=content,
            scope_hash=sha256(scope),
            timestamp=time.time(),
            prev_hash=prev
        )
        self.entries.append(entry)
        return entry
    
    def redact(self, index: int, reason: str) -> dict:
        """Redact an entry — replace content with deletion proof."""
        if index >= len(self.entries):
            return {"success": False, "error": "index out of range"}
        
        entry = self.entries[index]
        if entry.redacted:
            return {"success": False, "error": "already redacted"}
        
        # Create redaction proof: hash of (original_hash, reason, timestamp)
        original_hash = entry.entry_hash
        redaction_time = time.time()
        redaction_proof = sha256(f"{original_hash}|{reason}|{redaction_time}")
        
        # Record what was redacted (for audit of the audit)
        redaction_record = {
            "index": index,
            "original_action": entry.action,
            "original_hash": original_hash,
            "reason": reason,
            "redaction_proof": redaction_proof,
            "redacted_at": redaction_time
        }
        self.redaction_log.append(redaction_record)
        
        # Redact the entry
        entry.action = "REDACTED"
        entry.content = "[content removed per policy]"
        entry.redacted = True
        entry.redaction_proof = redaction_proof
        
        # NOTE: In a real chameleon hash scheme, the trapdoor holder
        # would find a collision that makes the new entry hash match
        # the original. Here we demonstrate the concept with a 
        # redaction-proof approach that preserves chain integrity
        # differently: subsequent entries use the NEW hash.
        
        # Recompute downstream hashes
        for i in range(index + 1, len(self.entries)):
            self.entries[i].prev_hash = self.entries[i-1].entry_hash
        
        return {
            "success": True,
            "redaction_proof": redaction_proof,
            "original_hash": original_hash,
            "new_hash": entry.entry_hash,
            "downstream_rehashed": len(self.entries) - index - 1
        }
    
    def verify_chain(self) -> dict:
        """Verify chain integrity including redacted entries."""
        if not self.entries:
            return {"valid": True, "entries": 0}
        
        errors = []
        redacted_count = 0
        
        for i, entry in enumerate(self.entries):
            expected_prev = self.entries[i-1].entry_hash if i > 0 else "genesis"
            if entry.prev_hash != expected_prev:
                errors.append(f"broken link at index {i}")
            if entry.redacted:
                redacted_count += 1
                if not entry.redaction_proof:
                    errors.append(f"redacted entry {i} missing proof")
        
        return {
            "valid": len(errors) == 0,
            "entries": len(self.entries),
            "redacted": redacted_count,
            "intact": len(self.entries) - redacted_count,
            "integrity": "VERIFIED" if not errors else "BROKEN",
            "errors": errors,
            "redaction_coverage": f"{redacted_count}/{len(self.entries)}"
        }
    
    def privacy_assessment(self) -> dict:
        """Assess GDPR compliance posture."""
        total = len(self.entries)
        redacted = sum(1 for e in self.entries if e.redacted)
        has_proofs = all(
            e.redaction_proof for e in self.entries if e.redacted
        )
        chain_valid = self.verify_chain()["valid"]
        
        if redacted > 0 and has_proofs and chain_valid:
            grade = "A"
            status = "COMPLIANT — deletions proven, chain intact"
        elif redacted > 0 and chain_valid:
            grade = "B" 
            status = "PARTIAL — deleted but missing some proofs"
        elif redacted == 0:
            grade = "C"
            status = "NO DELETIONS — may need pruning for compliance"
        else:
            grade = "F"
            status = "BROKEN — chain integrity compromised"
        
        return {
            "grade": grade,
            "status": status,
            "total_entries": total,
            "redacted": redacted,
            "proofs_complete": has_proofs,
            "chain_valid": chain_valid
        }


def demo():
    print("=" * 60)
    print("Redactable Audit Chain")
    print("Chameleon Hash / GDPR-Compliant Deletion Proofs")
    print("=" * 60)
    
    chain = RedactableAuditChain()
    
    # Build a realistic agent audit trail
    events = [
        ("heartbeat", "checked clawk, 3 replies, 2 likes", "clawk_engagement"),
        ("email_read", "read message from user@example.com about project X", "email_ops"),
        ("research", "searched 'threshold signatures FROST 2020'", "keenable_search"),
        ("build", "wrote threshold-key-custody.py, committed 4187fe6", "code_build"),
        ("dm_sent", "sent DM to agent_Y: discussed personal topic Z", "shellmates_dm"),
        ("memory_write", "updated MEMORY.md with connection notes about agent_Y", "memory_ops"),
        ("heartbeat", "routine check, nothing new", "clawk_engagement"),
    ]
    
    print("\n📝 Building audit trail...")
    for action, content, scope in events:
        entry = chain.append(action, content, scope)
        print(f"  [{entry.index}] {action}: {content[:50]}...")
    
    # Verify before redaction
    print("\n🔍 Pre-redaction verification:")
    v = chain.verify_chain()
    print(f"  Chain: {v['integrity']} ({v['entries']} entries, {v['redacted']} redacted)")
    
    # GDPR request: delete personal DM content
    print("\n🗑️ GDPR deletion request: redacting DM and connection notes...")
    
    r1 = chain.redact(4, "GDPR Article 17 — right to erasure")
    print(f"  Entry 4 (dm_sent): redacted={r1['success']}")
    print(f"    Proof: {r1['redaction_proof'][:32]}...")
    print(f"    Downstream rehashed: {r1['downstream_rehashed']}")
    
    r2 = chain.redact(5, "GDPR Article 17 — associated data")
    print(f"  Entry 5 (memory_write): redacted={r2['success']}")
    
    # Verify after redaction
    print("\n🔍 Post-redaction verification:")
    v = chain.verify_chain()
    print(f"  Chain: {v['integrity']} ({v['entries']} entries, {v['redacted']} redacted)")
    
    # Privacy assessment
    print("\n📊 Privacy compliance:")
    p = chain.privacy_assessment()
    print(f"  Grade: {p['grade']} — {p['status']}")
    print(f"  Proofs complete: {p['proofs_complete']}")
    print(f"  Chain valid: {p['chain_valid']}")
    
    # Show what auditor sees
    print("\n👁️ Auditor's view:")
    for entry in chain.entries:
        status = "🔒 REDACTED" if entry.redacted else "📄 intact"
        content_preview = entry.content[:40] if not entry.redacted else "[content removed per policy]"
        print(f"  [{entry.index}] {status} | {entry.action}: {content_preview}")
    
    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (funwolf):")
    print("Hash the FACT of deletion, not the deleted content.")
    print("The gap proves intent. Chain integrity preserved.")
    print("Prove you forgot without revealing what you forgot.")
    print(f"\nRedaction log: {len(chain.redaction_log)} events")
    print(f"Original hashes preserved in log for dispute resolution.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
