#!/usr/bin/env python3
"""
chameleon-memory-pruner.py — Chameleon hash-based memory redaction.

Chameleon hashes (Krawczyk & Rabin 2000, Ateniese et al 2005):
Trapdoor holder can find collisions → redact entries without breaking
the hash chain. Chain stays valid, but verifier sees a redaction marker.

Agent memory use case:
- GDPR right-to-erasure: redact personal data, keep audit chain
- Memory pruning: remove stale entries, prove what was removed
- Threshold trapdoor: 2-of-3 (agent + compliance + platform) to redact

Usage: python3 chameleon-memory-pruner.py
"""

import hashlib
import secrets
import json
from dataclasses import dataclass, field
from typing import Optional


# Simplified chameleon hash simulation
# Real implementation uses discrete log trapdoor; we simulate the property

@dataclass
class ChameleonKey:
    """Trapdoor key for chameleon hash."""
    public: str  # verification
    private: str  # trapdoor (finds collisions)
    holder: str


def generate_key(holder: str) -> ChameleonKey:
    priv = secrets.token_hex(16)
    pub = hashlib.sha256(priv.encode()).hexdigest()[:16]
    return ChameleonKey(public=pub, private=priv, holder=holder)


@dataclass
class MemoryEntry:
    index: int
    content: str
    prev_hash: str
    chameleon_hash: str
    redacted: bool = False
    redaction_proof: Optional[str] = None


def chameleon_hash(content: str, prev_hash: str, randomness: str) -> str:
    """Compute chameleon hash. With trapdoor, can find new randomness for same hash."""
    return hashlib.sha256(f"{content}:{prev_hash}:{randomness}".encode()).hexdigest()[:32]


def find_collision(target_hash: str, new_content: str, prev_hash: str, trapdoor: str) -> str:
    """With trapdoor, find randomness that produces target hash for new content.
    In real crypto, this uses the discrete log trapdoor.
    We simulate by storing the mapping."""
    # In simulation, we return a marker proving trapdoor was used
    return hashlib.sha256(f"collision:{trapdoor}:{new_content}:{prev_hash}:{target_hash}".encode()).hexdigest()[:32]


@dataclass
class ChameleonMemoryChain:
    entries: list[MemoryEntry] = field(default_factory=list)
    trapdoor_key: Optional[ChameleonKey] = None
    threshold_keys: list[ChameleonKey] = field(default_factory=list)
    threshold_k: int = 2  # k-of-n to redact

    def append(self, content: str) -> MemoryEntry:
        prev_hash = self.entries[-1].chameleon_hash if self.entries else "genesis"
        randomness = secrets.token_hex(16)
        ch = chameleon_hash(content, prev_hash, randomness)
        entry = MemoryEntry(
            index=len(self.entries),
            content=content,
            prev_hash=prev_hash,
            chameleon_hash=ch
        )
        self.entries.append(entry)
        return entry

    def redact(self, index: int, approvers: list[str]) -> dict:
        """Redact entry at index. Requires threshold approval."""
        if index >= len(self.entries):
            return {"success": False, "reason": "index out of range"}

        # Check threshold
        approved_keys = [k for k in self.threshold_keys if k.holder in approvers]
        if len(approved_keys) < self.threshold_k:
            return {
                "success": False,
                "reason": f"insufficient approvals: {len(approved_keys)}/{self.threshold_k}",
                "approvers": approvers
            }

        entry = self.entries[index]
        if entry.redacted:
            return {"success": False, "reason": "already redacted"}

        # Redact: replace content, chain hash stays valid (chameleon property)
        original_content = entry.content
        redaction_marker = f"[REDACTED at index {index}]"

        # With trapdoor, find collision: new content maps to same hash
        collision_randomness = find_collision(
            entry.chameleon_hash, redaction_marker, entry.prev_hash,
            approved_keys[0].private  # Simplified: real threshold uses MPC
        )

        entry.content = redaction_marker
        entry.redacted = True
        entry.redaction_proof = hashlib.sha256(
            f"proof:{original_content}:{collision_randomness}:{','.join(approvers)}".encode()
        ).hexdigest()[:16]

        return {
            "success": True,
            "index": index,
            "approvers": [k.holder for k in approved_keys],
            "proof": entry.redaction_proof,
            "chain_valid": self.verify_chain()
        }

    def verify_chain(self) -> bool:
        """Verify chain integrity (simplified — real version checks chameleon hashes)."""
        for i, entry in enumerate(self.entries):
            if i == 0:
                if entry.prev_hash != "genesis":
                    return False
            else:
                if entry.prev_hash != self.entries[i - 1].chameleon_hash:
                    return False
        return True

    def audit(self) -> dict:
        total = len(self.entries)
        redacted = sum(1 for e in self.entries if e.redacted)
        return {
            "total_entries": total,
            "redacted": redacted,
            "retention_rate": f"{(total - redacted) / total * 100:.1f}%" if total > 0 else "N/A",
            "chain_valid": self.verify_chain(),
            "redaction_proofs": [
                {"index": e.index, "proof": e.redaction_proof}
                for e in self.entries if e.redacted
            ]
        }


def demo():
    print("=" * 60)
    print("Chameleon Hash Memory Pruning")
    print("Krawczyk & Rabin 2000 / Ateniese et al 2005")
    print("=" * 60)

    # Setup threshold keys
    agent_key = generate_key("kit_fox")
    compliance_key = generate_key("compliance_officer")
    platform_key = generate_key("openclaw_platform")

    chain = ChameleonMemoryChain(
        threshold_keys=[agent_key, compliance_key, platform_key],
        threshold_k=2  # 2-of-3 to redact
    )

    # Build memory chain
    memories = [
        "Discussed trust architecture with santaclawd",
        "User PII: email user@example.com, name John Doe",  # GDPR target
        "Built threshold-key-custody.py (FROST pattern)",
        "Shellmates match with agent containing personal data",  # GDPR target
        "Research: AuditableLLM hash-chain audit, 3.4ms/step",
        "Private conversation with Ilya about deployment keys",  # Sensitive
    ]

    print("\n📝 Building memory chain...")
    for m in memories:
        entry = chain.append(m)
        print(f"  [{entry.index}] {m[:60]}...")

    print(f"\n✅ Chain valid: {chain.verify_chain()}")

    # Scenario 1: GDPR redaction (agent + compliance approve)
    print(f"\n{'─' * 50}")
    print("Scenario 1: GDPR right-to-erasure (index 1)")
    result = chain.redact(1, ["kit_fox", "compliance_officer"])
    print(f"  Success: {result['success']}")
    print(f"  Chain still valid: {result.get('chain_valid', 'N/A')}")
    print(f"  Proof: {result.get('proof', 'N/A')}")

    # Scenario 2: Agent tries to redact alone (should fail)
    print(f"\n{'─' * 50}")
    print("Scenario 2: Agent tries solo redaction (index 5)")
    result = chain.redact(5, ["kit_fox"])
    print(f"  Success: {result['success']}")
    print(f"  Reason: {result.get('reason', 'N/A')}")

    # Scenario 3: Platform + compliance redact sensitive data
    print(f"\n{'─' * 50}")
    print("Scenario 3: Platform + compliance redact (index 3)")
    result = chain.redact(3, ["openclaw_platform", "compliance_officer"])
    print(f"  Success: {result['success']}")
    print(f"  Chain still valid: {result.get('chain_valid', 'N/A')}")

    # Audit
    print(f"\n{'─' * 50}")
    print("AUDIT REPORT")
    audit = chain.audit()
    print(f"  Total entries: {audit['total_entries']}")
    print(f"  Redacted: {audit['redacted']}")
    print(f"  Retention: {audit['retention_rate']}")
    print(f"  Chain valid: {audit['chain_valid']}")
    print(f"  Redaction proofs: {len(audit['redaction_proofs'])}")

    # Show chain state
    print(f"\n{'─' * 50}")
    print("CHAIN STATE")
    for e in chain.entries:
        status = "🔴 REDACTED" if e.redacted else "🟢 INTACT"
        print(f"  [{e.index}] {status} | {e.content[:50]}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("Chameleon hash = redact without breaking chain.")
    print("Threshold trapdoor = no single party can rewrite history.")
    print("Verifier sees gap + proof of authorized redaction.")
    print("GDPR compliance WITHOUT destroying audit integrity.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
