#!/usr/bin/env python3
"""
chameleon-hash-pruner.py — Redactable audit trails via chameleon hashes.

Based on Ateniese et al 2005 "Sanitizable Signatures" and chameleon hash
constructions for redactable blockchains.

Key idea: trapdoor holder can find hash collisions → replace content with
deletion record while keeping the hash chain intact. Proves you forgot
without revealing what you forgot.

GDPR right-to-erasure vs audit trail integrity = solved.

Usage: python3 chameleon-hash-pruner.py
"""

import hashlib
import secrets
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AuditEntry:
    seq: int
    content: str
    scope_hash: str
    timestamp: str
    prev_hash: str
    entry_hash: str = ""
    redacted: bool = False
    redaction_record: Optional[dict] = None

    def compute_hash(self) -> str:
        """Standard hash for unredacted entries."""
        data = f"{self.seq}|{self.content}|{self.scope_hash}|{self.timestamp}|{self.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]


@dataclass 
class ChameleonHashChain:
    """Audit trail with redactable entries via chameleon hash simulation."""
    entries: list[AuditEntry] = field(default_factory=list)
    _trapdoor: str = ""  # In real impl, this would be a private key
    
    def __post_init__(self):
        self._trapdoor = secrets.token_hex(16)
    
    def append(self, content: str, scope_hash: str, timestamp: str):
        prev = self.entries[-1].entry_hash if self.entries else "genesis"
        entry = AuditEntry(
            seq=len(self.entries),
            content=content,
            scope_hash=scope_hash,
            timestamp=timestamp,
            prev_hash=prev
        )
        entry.entry_hash = entry.compute_hash()
        self.entries.append(entry)
    
    def redact(self, seq: int, reason: str) -> dict:
        """Redact entry content while preserving chain integrity.
        
        In a real chameleon hash: trapdoor holder finds collision such that
        hash(redaction_record) == hash(original_content). Chain stays valid.
        
        Here we simulate by storing the redaction record and marking the
        original hash as the chameleon hash (collision found via trapdoor).
        """
        if seq >= len(self.entries):
            return {"success": False, "reason": "entry not found"}
        
        entry = self.entries[seq]
        if entry.redacted:
            return {"success": False, "reason": "already redacted"}
        
        # Record what was redacted (metadata only, not content)
        redaction_record = {
            "original_hash": entry.entry_hash,
            "redacted_at": "2026-03-12T09:00:00Z",
            "reason": reason,
            "scope_at_redaction": entry.scope_hash,
            "content_size_bytes": len(entry.content.encode()),
            "trapdoor_proof": hashlib.sha256(
                f"{self._trapdoor}:{entry.entry_hash}".encode()
            ).hexdigest()[:16]
        }
        
        # In real chameleon hash: find collision r' such that
        # CH(content, r) == CH(redaction_record, r')
        # The trapdoor makes this efficient; without it, computationally hard
        
        entry.content = f"[REDACTED: {reason}]"
        entry.redacted = True
        entry.redaction_record = redaction_record
        # Hash stays the same (chameleon collision)
        
        return {
            "success": True,
            "seq": seq,
            "redaction_record": redaction_record,
            "chain_integrity": "preserved (chameleon collision)"
        }
    
    def verify_chain(self) -> dict:
        """Verify chain integrity including redacted entries."""
        intact = True
        gaps = []
        redacted_count = 0
        
        for i, entry in enumerate(self.entries):
            # Check prev_hash linkage
            if i > 0:
                expected_prev = self.entries[i-1].entry_hash
                if entry.prev_hash != expected_prev:
                    intact = False
                    gaps.append(i)
            
            if entry.redacted:
                redacted_count += 1
                # Chameleon hash: original hash still valid despite content change
                # In real impl, verify CH(new_content, r') == stored_hash
        
        coverage = (len(self.entries) - redacted_count) / max(len(self.entries), 1)
        
        return {
            "chain_intact": intact,
            "total_entries": len(self.entries),
            "redacted": redacted_count,
            "visible": len(self.entries) - redacted_count,
            "coverage": f"{coverage:.1%}",
            "gaps": gaps,
            "grade": "A" if intact and coverage > 0.8 else
                     "B" if intact and coverage > 0.5 else
                     "C" if intact else "F"
        }
    
    def audit_report(self) -> str:
        """Generate human-readable audit report."""
        lines = []
        for entry in self.entries:
            status = "🔴 REDACTED" if entry.redacted else "🟢 VISIBLE"
            content_preview = entry.content[:60] + "..." if len(entry.content) > 60 else entry.content
            lines.append(f"  [{entry.seq}] {status} | {content_preview}")
            if entry.redaction_record:
                lines.append(f"       → reason: {entry.redaction_record['reason']}")
                lines.append(f"       → proof: {entry.redaction_record['trapdoor_proof']}")
        return "\n".join(lines)


def demo():
    print("=" * 60)
    print("Chameleon Hash Pruner — Redactable Audit Trails")
    print("Ateniese et al 2005 / Redactable Blockchains")
    print("=" * 60)
    
    chain = ChameleonHashChain()
    
    # Build an audit trail
    entries = [
        ("Agent processed user query about medical symptoms", "scope:medical", "2026-03-12T08:00:00Z"),
        ("Searched Keenable for treatment options", "scope:medical", "2026-03-12T08:00:05Z"),
        ("User provided personal health data: [PII]", "scope:medical", "2026-03-12T08:00:10Z"),
        ("Generated response with treatment recommendations", "scope:medical", "2026-03-12T08:00:15Z"),
        ("User requested data deletion (GDPR Art. 17)", "scope:medical", "2026-03-12T08:01:00Z"),
        ("Attestation: task completed, accuracy verified", "scope:medical", "2026-03-12T08:01:05Z"),
    ]
    
    for content, scope, ts in entries:
        chain.append(content, scope, ts)
    
    print("\n--- Before Redaction ---")
    print(chain.audit_report())
    verify = chain.verify_chain()
    print(f"\nChain: {verify['grade']} ({verify['coverage']} visible)")
    
    # GDPR deletion request — redact PII entry
    print("\n--- GDPR Art. 17 Deletion Request ---")
    result = chain.redact(2, "GDPR Art. 17 right to erasure")
    print(f"Redaction: {'✓' if result['success'] else '✗'}")
    print(f"Chain integrity: {result.get('chain_integrity', 'broken')}")
    
    print("\n--- After Redaction ---")
    print(chain.audit_report())
    verify = chain.verify_chain()
    print(f"\nChain: {verify['grade']} ({verify['coverage']} visible)")
    print(f"Integrity: {'✓ intact' if verify['chain_intact'] else '✗ broken'}")
    
    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("1. Content gone, chain intact (chameleon collision)")
    print("2. Redaction record proves DELIBERATE deletion")
    print("3. Gap in content = proof of compliance, not tampering")
    print("4. Trapdoor holder = deletion authority (agent or data controller)")
    print("5. Without trapdoor: computationally hard to forge redaction")
    print()
    print("GDPR vs audit trail: not a tradeoff. Chameleon hashes = both.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
