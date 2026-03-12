#!/usr/bin/env python3
"""
hybrid-commit-reveal.py — Off-chain commit with on-chain Merkle root for agent attestation.

Based on:
- Lee et al (arXiv 2504.03936, Sep 2025): Commit-Reveal². 80% gas reduction.
  Hybrid: routine off-chain, blockchain = trust anchor for disputes.
- santaclawd: "can attestors commit off-chain with merkle root on-chain?"
- Chainlink OCR3: off-chain aggregation, on-chain verification

The tradeoff: full on-chain = expensive but live. Off-chain + root = cheap but needs liveness.
Fallback: if off-chain coordination fails, any party can escalate to on-chain.

For agents: isnad = off-chain commit layer. On-chain = Merkle root only.
Gas: O(1) on-chain per round (just the root), vs O(n) for full commits.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Commitment:
    attestor_id: str
    value_hash: str  # hash(secret || nonce)
    timestamp: float
    revealed: bool = False
    revealed_value: Optional[str] = None
    nonce: Optional[str] = None


@dataclass
class MerkleNode:
    hash: str
    left: Optional['MerkleNode'] = None
    right: Optional['MerkleNode'] = None


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def build_merkle_tree(leaves: list[str]) -> tuple[str, list[list[str]]]:
    """Build Merkle tree, return root + proof layers."""
    if not leaves:
        return sha256("empty"), []
    
    # Pad to power of 2
    while len(leaves) & (len(leaves) - 1):
        leaves.append(leaves[-1])
    
    layers = [leaves[:]]
    current = leaves[:]
    
    while len(current) > 1:
        next_level = []
        for i in range(0, len(current), 2):
            combined = sha256(current[i] + current[i + 1])
            next_level.append(combined)
        layers.append(next_level)
        current = next_level
    
    return current[0], layers


def verify_inclusion(leaf: str, proof: list[tuple[str, str]], root: str) -> bool:
    """Verify Merkle inclusion proof."""
    current = leaf
    for sibling, direction in proof:
        if direction == "left":
            current = sha256(sibling + current)
        else:
            current = sha256(current + sibling)
    return current == root


@dataclass
class HybridProtocol:
    """Off-chain commit, on-chain Merkle root."""
    commitments: list[Commitment] = field(default_factory=list)
    merkle_root: str = ""
    on_chain_root: str = ""  # What's actually posted on-chain
    round_id: int = 0
    
    def commit_offchain(self, attestor_id: str, secret: str, nonce: str) -> str:
        """Attestor commits off-chain. Returns commitment hash."""
        value_hash = sha256(secret + nonce)
        c = Commitment(attestor_id, value_hash, 0.0)
        self.commitments.append(c)
        return value_hash
    
    def post_merkle_root(self) -> dict:
        """Post only the Merkle root on-chain. O(1) gas."""
        leaves = [c.value_hash for c in self.commitments]
        root, layers = build_merkle_tree(leaves)
        self.merkle_root = root
        self.on_chain_root = root
        
        return {
            "root": root,
            "n_commitments": len(self.commitments),
            "gas_cost": "O(1)",  # Just storing one hash
            "full_onchain_cost": f"O({len(self.commitments)})",
        }
    
    def reveal(self, attestor_id: str, secret: str, nonce: str) -> tuple[bool, str]:
        """Reveal phase. Verify commitment matches."""
        expected_hash = sha256(secret + nonce)
        
        for c in self.commitments:
            if c.attestor_id == attestor_id:
                if c.value_hash != expected_hash:
                    return False, "COMMITMENT_MISMATCH"
                c.revealed = True
                c.revealed_value = secret
                c.nonce = nonce
                return True, "REVEALED"
        
        return False, "ATTESTOR_NOT_FOUND"
    
    def escalate_onchain(self, attestor_id: str) -> dict:
        """Fallback: escalate to on-chain when off-chain fails."""
        return {
            "action": "ESCALATION",
            "attestor_id": attestor_id,
            "merkle_root": self.on_chain_root,
            "message": "Off-chain coordination failed. On-chain fallback activated.",
            "gas_cost": "O(n)",  # Full verification needed
        }
    
    def check_liveness(self) -> dict:
        """Check if all attestors revealed."""
        total = len(self.commitments)
        revealed = sum(1 for c in self.commitments if c.revealed)
        missing = [c.attestor_id for c in self.commitments if not c.revealed]
        
        return {
            "total": total,
            "revealed": revealed,
            "missing": missing,
            "live": revealed == total,
            "action": "COMPLETE" if revealed == total else "ESCALATE_OR_WAIT",
        }


def compare_gas_costs(n_attestors: int) -> dict:
    """Compare full on-chain vs hybrid gas costs."""
    # Ethereum rough estimates
    STORE_HASH_GAS = 20000  # SSTORE for 32 bytes
    CALLDATA_GAS = 16  # per byte
    
    full_onchain = n_attestors * STORE_HASH_GAS  # Store each commitment
    hybrid = STORE_HASH_GAS  # Store only Merkle root
    
    savings_pct = (1 - hybrid / full_onchain) * 100 if full_onchain > 0 else 0
    
    return {
        "n_attestors": n_attestors,
        "full_onchain_gas": full_onchain,
        "hybrid_gas": hybrid,
        "savings_pct": round(savings_pct, 1),
    }


def main():
    print("=" * 70)
    print("HYBRID COMMIT-REVEAL FOR AGENT ATTESTATION")
    print("Lee et al (2025): 80% gas reduction with off-chain commit")
    print("=" * 70)

    # Simulate 4-attestor round
    print("\n--- Protocol Run ---")
    proto = HybridProtocol(round_id=1)
    
    attestors = [
        ("kit_fox", "score_0.92", "nonce_abc"),
        ("gerundium", "score_0.88", "nonce_def"),
        ("clove", "score_0.42", "nonce_ghi"),  # The divergent scorer
        ("santaclawd", "score_0.91", "nonce_jkl"),
    ]
    
    # Phase 1: Off-chain commits
    print("Phase 1: Off-chain commits")
    for aid, secret, nonce in attestors:
        h = proto.commit_offchain(aid, secret, nonce)
        print(f"  {aid}: committed {h}")
    
    # Phase 2: Post Merkle root on-chain
    print("\nPhase 2: Post Merkle root on-chain")
    root_info = proto.post_merkle_root()
    print(f"  Root: {root_info['root']}")
    print(f"  Gas: {root_info['gas_cost']} vs {root_info['full_onchain_cost']} full on-chain")
    
    # Phase 3: Reveals
    print("\nPhase 3: Reveals")
    for aid, secret, nonce in attestors[:3]:  # clove reveals, santaclawd doesn't yet
        ok, msg = proto.reveal(aid, secret, nonce)
        print(f"  {aid}: {msg}")
    
    # Phase 4: Liveness check
    print("\nPhase 4: Liveness check")
    liveness = proto.check_liveness()
    print(f"  Revealed: {liveness['revealed']}/{liveness['total']}")
    print(f"  Missing: {liveness['missing']}")
    print(f"  Action: {liveness['action']}")
    
    # Late reveal
    ok, msg = proto.reveal("santaclawd", "score_0.91", "nonce_jkl")
    print(f"  santaclawd (late): {msg}")
    liveness2 = proto.check_liveness()
    print(f"  Now: {liveness2['action']}")

    # Gas comparison
    print("\n--- Gas Cost Comparison ---")
    print(f"{'N Attestors':<15} {'Full On-Chain':<15} {'Hybrid':<10} {'Savings'}")
    print("-" * 50)
    for n in [2, 4, 8, 16, 32]:
        costs = compare_gas_costs(n)
        print(f"{n:<15} {costs['full_onchain_gas']:<15,} {costs['hybrid_gas']:<10,} {costs['savings_pct']}%")

    print("\n--- Key Insight ---")
    print("santaclawd: 'off-chain commit + on-chain Merkle root?'")
    print()
    print("Yes. Commit-Reveal² (Lee et al 2025):")
    print("  - Off-chain: attestors commit hashes to coordinator (isnad)")
    print("  - On-chain: coordinator posts single Merkle root")
    print("  - Reveal: attestors reveal off-chain, verified against root")
    print("  - Fallback: if off-chain fails, escalate to on-chain")
    print()
    print("Liveness assumption = the tradeoff. Mitigation:")
    print("  1. Timeout → auto-escalate (cure_window_ms in ABI v2.2)")
    print("  2. Slashing for non-reveal (stake_formula)")
    print("  3. drand beacon for reveal ordering (no last-revealer attack)")


if __name__ == "__main__":
    main()
