#!/usr/bin/env python3
"""
chameleon-audit.py — Redactable audit trail using chameleon hash simulation.

Based on:
- Ateniese et al 2017 (Eurocrypt): Redactable Blockchain via Chameleon Hash
- Derler et al 2019 (NDSS): Fine-Grained and Controlled Rewriting in Blockchains

Problem: GDPR right-to-erasure vs immutable audit trail.
Solution: Chameleon hash allows redaction while preserving chain integrity.
The TOMBSTONE proves deletion happened without revealing deleted content.

Agent application: Memory pruning with provable deletion.
- Prove you forgot without revealing what you forgot
- Hash chain integrity survives redaction
- Tombstone = attestation of deliberate forgetting

Usage: python3 chameleon-audit.py
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
    content: str
    scope_hash: str
    timestamp: float
    prev_hash: str
    entry_hash: str = ""
    redacted: bool = False
    tombstone: Optional[str] = None

    def compute_hash(self) -> str:
        """Standard hash — non-redactable."""
        data = f"{self.index}:{self.action}:{self.content}:{self.scope_hash}:{self.timestamp}:{self.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def compute_chameleon_hash(self) -> str:
        """Chameleon hash — same output regardless of content redaction.
        
        In real implementation: trapdoor holder can find collisions.
        Here we simulate by hashing (index, action_type, scope, timestamp, prev)
        without content — the 'redaction-safe' components.
        """
        data = f"{self.index}:{self.action}:{self.scope_hash}:{self.timestamp}:{self.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]


@dataclass
class RedactableAuditTrail:
    entries: list[AuditEntry] = field(default_factory=list)
    use_chameleon: bool = True

    def append(self, action: str, content: str, scope: str) -> AuditEntry:
        prev_hash = self.entries[-1].entry_hash if self.entries else "genesis"
        entry = AuditEntry(
            index=len(self.entries),
            action=action,
            content=content,
            scope_hash=hashlib.sha256(scope.encode()).hexdigest()[:16],
            timestamp=time.time(),
            prev_hash=prev_hash
        )
        entry.entry_hash = entry.compute_chameleon_hash() if self.use_chameleon else entry.compute_hash()
        self.entries.append(entry)
        return entry

    def redact(self, index: int, reason: str) -> dict:
        """Redact entry content, preserve chain integrity."""
        if index >= len(self.entries):
            return {"success": False, "reason": "index out of range"}

        entry = self.entries[index]
        if entry.redacted:
            return {"success": False, "reason": "already redacted"}

        original_hash = entry.entry_hash
        original_content_hash = hashlib.sha256(entry.content.encode()).hexdigest()[:16]

        # Redact content
        entry.content = "[REDACTED]"
        entry.redacted = True
        entry.tombstone = json.dumps({
            "redacted_at": time.time(),
            "reason": reason,
            "content_fingerprint": original_content_hash,  # proves WHAT was deleted
            "chain_position": index
        })

        # With chameleon hash, entry_hash stays the same (content not in hash input)
        if self.use_chameleon:
            new_hash = entry.compute_chameleon_hash()
            integrity_preserved = (new_hash == original_hash)
        else:
            new_hash = entry.compute_hash()
            integrity_preserved = False  # Standard hash WILL change

        return {
            "success": True,
            "integrity_preserved": integrity_preserved,
            "original_hash": original_hash,
            "post_redaction_hash": new_hash,
            "tombstone": entry.tombstone,
            "content_fingerprint": original_content_hash
        }

    def verify_chain(self) -> dict:
        """Verify chain integrity including redacted entries."""
        if not self.entries:
            return {"valid": True, "entries": 0}

        broken_links = []
        redacted_count = 0

        for i, entry in enumerate(self.entries):
            # Check prev_hash linkage
            expected_prev = self.entries[i-1].entry_hash if i > 0 else "genesis"
            if entry.prev_hash != expected_prev:
                broken_links.append(i)

            # Re-verify entry hash
            expected_hash = entry.compute_chameleon_hash() if self.use_chameleon else entry.compute_hash()
            if entry.entry_hash != expected_hash:
                broken_links.append(i)

            if entry.redacted:
                redacted_count += 1

        return {
            "valid": len(broken_links) == 0,
            "entries": len(self.entries),
            "redacted": redacted_count,
            "broken_links": broken_links,
            "integrity": "FULL" if not broken_links else "BROKEN"
        }


def demo():
    print("=" * 60)
    print("Chameleon Hash Redactable Audit Trail")
    print("Ateniese 2017 / Derler 2019 (NDSS)")
    print("=" * 60)

    # Scenario 1: Chameleon hash (redaction-safe)
    print("\n--- Scenario 1: Chameleon Hash (redaction preserves integrity) ---")
    trail = RedactableAuditTrail(use_chameleon=True)

    trail.append("heartbeat", "checked clawk, 3 replies", "kit_fox:heartbeat")
    trail.append("post", "FROST threshold signatures for key custody", "kit_fox:clawk")
    trail.append("memory_write", "user shared private API key: sk-REDACTME", "kit_fox:memory")
    trail.append("reply", "cassian relay custody discussion", "kit_fox:clawk")
    trail.append("email", "bro_agent tc4 scope proposal", "kit_fox:agentmail")

    print(f"Entries: {len(trail.entries)}")
    pre = trail.verify_chain()
    print(f"Pre-redaction: {pre['integrity']} ({pre['entries']} entries)")

    # Redact the sensitive entry
    result = trail.redact(2, "GDPR: user requested deletion of API key")
    print(f"\nRedacted entry 2:")
    print(f"  Integrity preserved: {result['integrity_preserved']}")
    print(f"  Content fingerprint: {result['content_fingerprint']}")
    print(f"  Tombstone: present")

    post = trail.verify_chain()
    print(f"\nPost-redaction: {post['integrity']} ({post['redacted']} redacted)")

    # Scenario 2: Standard hash (redaction breaks chain)
    print("\n--- Scenario 2: Standard Hash (redaction BREAKS integrity) ---")
    trail2 = RedactableAuditTrail(use_chameleon=False)

    trail2.append("heartbeat", "checked platforms", "kit_fox:heartbeat")
    trail2.append("memory_write", "sensitive data here", "kit_fox:memory")
    trail2.append("post", "public post", "kit_fox:clawk")

    pre2 = trail2.verify_chain()
    print(f"Pre-redaction: {pre2['integrity']}")

    result2 = trail2.redact(1, "GDPR erasure request")
    print(f"Redacted entry 1: integrity preserved = {result2['integrity_preserved']}")

    post2 = trail2.verify_chain()
    print(f"Post-redaction: {post2['integrity']} (broken links: {post2['broken_links']})")

    # Scenario 3: Memory pruning
    print("\n--- Scenario 3: Agent Memory Pruning ---")
    trail3 = RedactableAuditTrail(use_chameleon=True)

    memories = [
        ("learn", "bro_agent thesis: infra encodes values", "kit_fox:memory"),
        ("learn", "santaclawd email about tc4 deliverable", "kit_fox:memory"),
        ("learn", "debugging session: moltbook captcha failures", "kit_fox:memory"),
        ("learn", "conversation about user's weekend plans", "kit_fox:memory"),
        ("learn", "key insight: compression is generative", "kit_fox:memory"),
    ]
    for action, content, scope in memories:
        trail3.append(action, content, scope)

    # Prune low-value memories
    pruned = [2, 3]  # debugging session + weekend plans
    for idx in pruned:
        trail3.redact(idx, "memory_pruning: low retention value")

    verify = trail3.verify_chain()
    print(f"Pruned {len(pruned)} memories, kept {verify['entries'] - verify['redacted']}")
    print(f"Chain integrity: {verify['integrity']}")
    print(f"Proof of forgetting: tombstones present for pruned entries")

    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("1. Chameleon hash: redact content, keep chain intact")
    print("2. Tombstone = proof of deletion without revealing content")
    print("3. Content fingerprint = prove WHAT was deleted (for audit)")
    print("4. Standard hash breaks on redaction — chameleon doesn't")
    print("5. Memory pruning = GDPR erasure with provable forgetting")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
