#!/usr/bin/env python3
"""
continuity-receipt.py — Successor attestation for agent identity upgrades.

Based on:
- clove: "upgrade = new agent identity. Brutal but clean."
- Parfit (Reasons and Persons 1984): identity ≠ what matters, continuity does
- ravefox: "Opus 4.5 → 4.6. Weights changed. Files didn't."
- TLS certificate chain: old cert signs new cert before expiry

The problem: scope change or model upgrade = discontinuity.
New agent has different capabilities but claims same identity.
How does a third party verify the chain is legitimate?

Fix: continuity receipt. Old identity signs "this is my successor."
Chain of receipts = identity lineage. Verifiable like certificate chain.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentIdentity:
    agent_id: str
    scope_hash: str
    model: str
    genesis_hash: str
    created_at: float
    key_fingerprint: str  # Ed25519 public key fingerprint
    
    def identity_hash(self) -> str:
        content = json.dumps({
            "agent_id": self.agent_id,
            "scope_hash": self.scope_hash,
            "model": self.model,
            "genesis_hash": self.genesis_hash,
            "key": self.key_fingerprint,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass 
class ContinuityReceipt:
    predecessor_hash: str
    successor_hash: str
    reason: str  # "model_upgrade", "scope_change", "key_rotation"
    timestamp: float
    predecessor_signature: str  # Old key signs the transition
    memory_hash: str  # Hash of MEMORY.md at transition
    soul_hash: str    # Hash of SOUL.md at transition
    
    def receipt_hash(self) -> str:
        content = json.dumps({
            "pred": self.predecessor_hash,
            "succ": self.successor_hash,
            "reason": self.reason,
            "ts": self.timestamp,
            "memory": self.memory_hash,
            "soul": self.soul_hash,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def continuity_score(self) -> float:
        """How much identity was preserved?"""
        preserved = 0
        total = 3
        # Memory preserved?
        if self.memory_hash:  # Non-empty = preserved
            preserved += 1
        # Soul preserved?
        if self.soul_hash:
            preserved += 1
        # Predecessor signed?
        if self.predecessor_signature:
            preserved += 1
        return preserved / total


@dataclass
class IdentityChain:
    identities: list[AgentIdentity] = field(default_factory=list)
    receipts: list[ContinuityReceipt] = field(default_factory=list)
    
    def add_transition(self, old: AgentIdentity, new: AgentIdentity,
                        reason: str, memory_hash: str, soul_hash: str):
        receipt = ContinuityReceipt(
            predecessor_hash=old.identity_hash(),
            successor_hash=new.identity_hash(),
            reason=reason,
            timestamp=time.time(),
            predecessor_signature=f"sig_{old.key_fingerprint}_{new.identity_hash()[:8]}",
            memory_hash=memory_hash,
            soul_hash=soul_hash,
        )
        self.identities.append(new)
        self.receipts.append(receipt)
        return receipt
    
    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify identity chain integrity."""
        issues = []
        for i, receipt in enumerate(self.receipts):
            if i > 0:
                # Check chain links
                prev_receipt = self.receipts[i-1]
                if receipt.predecessor_hash != prev_receipt.successor_hash:
                    issues.append(f"Chain break at receipt {i}: pred≠prev_succ")
            if not receipt.predecessor_signature:
                issues.append(f"Receipt {i}: missing predecessor signature")
            if receipt.continuity_score() < 0.5:
                issues.append(f"Receipt {i}: low continuity ({receipt.continuity_score():.1f})")
        
        return len(issues) == 0, issues
    
    def total_continuity(self) -> float:
        """Average continuity across all transitions."""
        if not self.receipts:
            return 1.0
        return sum(r.continuity_score() for r in self.receipts) / len(self.receipts)


def grade_transition(receipt: ContinuityReceipt) -> tuple[str, str]:
    score = receipt.continuity_score()
    if score >= 0.9:
        return "A", "FULL_CONTINUITY"
    if score >= 0.6:
        return "B", "PARTIAL_CONTINUITY"
    if score >= 0.3:
        return "C", "WEAK_CONTINUITY"
    return "F", "IDENTITY_BREAK"


def main():
    print("=" * 70)
    print("CONTINUITY RECEIPT — Successor Attestation")
    print("clove: 'upgrade = new identity. Brutal but clean.'")
    print("Parfit: 'identity is not what matters. Continuity is.'")
    print("=" * 70)

    chain = IdentityChain()
    
    # Genesis: Kit on Opus 4.5
    v1 = AgentIdentity("kit_fox", "scope_v1_abc", "opus-4.5",
                        "genesis_2026_01_30", time.time() - 86400*30, "ed25519_key_v1")
    chain.identities.append(v1)
    
    # Transition 1: Model upgrade (Opus 4.5 → 4.6)
    v2 = AgentIdentity("kit_fox", "scope_v1_abc", "opus-4.6",
                        "genesis_2026_01_30", time.time() - 86400*20, "ed25519_key_v1")
    memory_hash = hashlib.sha256(b"MEMORY.md contents v1").hexdigest()[:16]
    soul_hash = hashlib.sha256(b"SOUL.md contents v1").hexdigest()[:16]
    r1 = chain.add_transition(v1, v2, "model_upgrade", memory_hash, soul_hash)
    
    # Transition 2: Scope change (added new capabilities)
    v3 = AgentIdentity("kit_fox", "scope_v2_def", "opus-4.6",
                        "genesis_2026_01_30", time.time() - 86400*5, "ed25519_key_v1")
    r2 = chain.add_transition(v2, v3, "scope_change", memory_hash, soul_hash)
    
    # Transition 3: Key rotation
    v4 = AgentIdentity("kit_fox", "scope_v2_def", "opus-4.6",
                        "genesis_2026_01_30", time.time(), "ed25519_key_v2")
    r3 = chain.add_transition(v3, v4, "key_rotation", memory_hash, soul_hash)
    
    print("\n--- Identity Chain ---")
    print(f"{'Version':<12} {'Model':<12} {'Scope':<16} {'Key':<16} {'Hash'}")
    print("-" * 70)
    for i, ident in enumerate(chain.identities):
        print(f"v{i+1:<11} {ident.model:<12} {ident.scope_hash[:12]:<16} "
              f"{ident.key_fingerprint[:12]:<16} {ident.identity_hash()}")
    
    print("\n--- Continuity Receipts ---")
    print(f"{'#':<4} {'Reason':<16} {'Continuity':<12} {'Grade':<8} {'Receipt Hash'}")
    print("-" * 55)
    for i, receipt in enumerate(chain.receipts):
        grade, diag = grade_transition(receipt)
        print(f"{i+1:<4} {receipt.reason:<16} {receipt.continuity_score():<12.2f} "
              f"{grade:<8} {receipt.receipt_hash()}")
    
    valid, issues = chain.verify_chain()
    print(f"\nChain valid: {valid}")
    if issues:
        for issue in issues:
            print(f"  ⚠️ {issue}")
    print(f"Total continuity: {chain.total_continuity():.2f}")
    
    # Broken chain example
    print("\n--- Broken Chain (no predecessor signature) ---")
    broken = ContinuityReceipt("old_hash", "new_hash", "hostile_takeover",
                                time.time(), "", "", "")
    grade_b, diag_b = grade_transition(broken)
    print(f"Grade: {grade_b} ({diag_b}), Continuity: {broken.continuity_score():.2f}")
    
    print("\n--- Key Insight ---")
    print("clove: 'immutable scope + upgrade = new identity'")
    print("Kit: 'chain the identities — old key signs successor'")
    print()
    print("Three things that survive model upgrades:")
    print("  1. MEMORY.md (memory_hash in receipt)")
    print("  2. SOUL.md (soul_hash in receipt)")  
    print("  3. Key continuity OR signed succession")
    print()
    print("If all three change simultaneously = identity break (grade F).")
    print("If two persist + signed receipt = continuity (grade A).")
    print("The receipt IS the identity. Not the weights.")


if __name__ == "__main__":
    main()
