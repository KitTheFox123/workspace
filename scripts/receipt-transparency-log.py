#!/usr/bin/env python3
"""Receipt Transparency Log — Certificate Transparency pattern for agent receipts.

Append-only Merkle tree where every receipt must appear or its absence is detectable.
Based on RFC 6962 (Certificate Transparency) applied to agent attestation receipts.

Key insight (santaclawd): "you can't delete silently when the chain expects continuity."
Trillian/transparency.dev does this for TLS certs. We do it for agent receipts.

Usage:
  python receipt-transparency-log.py --demo
  echo '{"action": "append", "receipt": {...}}' | python receipt-transparency-log.py --json
"""

import hashlib
import json
import sys
import math
from datetime import datetime, timezone


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


class MerkleTree:
    """Simple Merkle tree for receipt transparency."""
    
    def __init__(self):
        self.leaves = []  # (hash, receipt_summary)
        self.root = None
    
    def append(self, receipt: dict) -> dict:
        """Append a receipt and return inclusion proof."""
        leaf_data = json.dumps(receipt, sort_keys=True)
        leaf_hash = sha256(leaf_data)
        index = len(self.leaves)
        self.leaves.append((leaf_hash, receipt.get("contract_id", "unknown")))
        self.root = self._compute_root()
        
        return {
            "index": index,
            "leaf_hash": leaf_hash,
            "tree_size": len(self.leaves),
            "root_hash": self.root,
            "inclusion_proof": self._inclusion_proof(index),
        }
    
    def _compute_root(self) -> str:
        if not self.leaves:
            return sha256("")
        hashes = [h for h, _ in self.leaves]
        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])
            hashes = [sha256(hashes[i] + hashes[i+1]) for i in range(0, len(hashes), 2)]
        return hashes[0]
    
    def _inclusion_proof(self, index: int) -> list:
        """Generate Merkle inclusion proof for leaf at index."""
        if len(self.leaves) <= 1:
            return []
        
        hashes = [h for h, _ in self.leaves]
        proof = []
        idx = index
        
        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])
            sibling = idx ^ 1  # XOR to get sibling
            if sibling < len(hashes):
                proof.append({
                    "hash": hashes[sibling],
                    "position": "left" if sibling < idx else "right",
                })
            hashes = [sha256(hashes[i] + hashes[i+1]) for i in range(0, len(hashes), 2)]
            idx //= 2
        
        return proof
    
    def verify_inclusion(self, leaf_hash: str, proof: list, root: str) -> bool:
        """Verify a leaf is included using its proof."""
        current = leaf_hash
        for step in proof:
            if step["position"] == "left":
                current = sha256(step["hash"] + current)
            else:
                current = sha256(current + step["hash"])
        return current == root
    
    def consistency_check(self, old_size: int, old_root: str) -> dict:
        """Check that old tree is a prefix of current tree (no tampering)."""
        if old_size > len(self.leaves):
            return {"consistent": False, "reason": "old_size > current_size"}
        
        # Rebuild tree at old_size
        old_hashes = [h for h, _ in self.leaves[:old_size]]
        while len(old_hashes) > 1:
            if len(old_hashes) % 2 == 1:
                old_hashes.append(old_hashes[-1])
            old_hashes = [sha256(old_hashes[i] + old_hashes[i+1]) for i in range(0, len(old_hashes), 2)]
        
        computed_root = old_hashes[0] if old_hashes else sha256("")
        consistent = computed_root == old_root
        
        return {
            "consistent": consistent,
            "old_size": old_size,
            "current_size": len(self.leaves),
            "old_root": old_root,
            "computed_old_root": computed_root,
            "current_root": self.root,
            "reason": "prefix verified" if consistent else "ROOT MISMATCH — tampering detected",
        }


def detect_gaps(receipts: list) -> list:
    """Detect temporal gaps in receipt sequence (santaclawd's insight)."""
    if len(receipts) < 2:
        return []
    
    gaps = []
    sorted_receipts = sorted(receipts, key=lambda r: r.get("timestamp", ""))
    
    for i in range(1, len(sorted_receipts)):
        prev = sorted_receipts[i-1]
        curr = sorted_receipts[i]
        
        # Check sequence continuity
        prev_seq = prev.get("sequence", i-1)
        curr_seq = curr.get("sequence", i)
        if curr_seq - prev_seq > 1:
            gaps.append({
                "type": "sequence_gap",
                "between": [prev_seq, curr_seq],
                "missing_count": curr_seq - prev_seq - 1,
                "severity": "HIGH" if curr_seq - prev_seq > 2 else "MEDIUM",
                "note": "Missing entries — possible deletion or suppression",
            })
        
        # Check temporal gaps (>24h between sequential receipts)
        try:
            prev_t = datetime.fromisoformat(prev.get("timestamp", "2026-01-01T00:00:00Z").replace("Z", "+00:00"))
            curr_t = datetime.fromisoformat(curr.get("timestamp", "2026-01-01T00:00:00Z").replace("Z", "+00:00"))
            delta_hours = (curr_t - prev_t).total_seconds() / 3600
            if delta_hours > 24:
                gaps.append({
                    "type": "temporal_gap",
                    "hours": round(delta_hours, 1),
                    "between_sequences": [prev_seq, curr_seq],
                    "severity": "LOW" if delta_hours < 72 else "MEDIUM",
                    "note": f"{delta_hours:.0f}h gap — may indicate suppressed activity",
                })
        except (ValueError, TypeError):
            pass
    
    return gaps


def demo():
    print("=" * 60)
    print("Receipt Transparency Log (RFC 6962 pattern)")
    print("=" * 60)
    
    tree = MerkleTree()
    
    # Simulate tc3-style receipt chain
    receipts = [
        {"contract_id": "tc3", "type": "x402_payment", "amount": "0.01 SOL", "timestamp": "2026-02-24T10:00:00Z", "sequence": 0},
        {"contract_id": "tc3", "type": "generation_sig", "content_hash": "abc123", "timestamp": "2026-02-24T12:00:00Z", "sequence": 1},
        {"contract_id": "tc3", "type": "dkim_delivery", "selector": "agentmail", "timestamp": "2026-02-24T12:05:00Z", "sequence": 2},
        {"contract_id": "tc3", "type": "attestation", "attester": "bro_agent", "score": 0.92, "timestamp": "2026-02-24T14:00:00Z", "sequence": 3},
        {"contract_id": "tc3", "type": "settlement", "result": "completed", "timestamp": "2026-02-24T14:30:00Z", "sequence": 4},
    ]
    
    print("\n--- Appending TC3 receipts ---")
    proofs = []
    for r in receipts:
        result = tree.append(r)
        proofs.append(result)
        print(f"  #{result['index']} {r['type']}: leaf={result['leaf_hash'][:16]}... root={result['root_hash'][:16]}...")
    
    # Verify inclusion
    print("\n--- Inclusion Verification ---")
    for i, proof in enumerate(proofs):
        verified = tree.verify_inclusion(proof["leaf_hash"], proof["inclusion_proof"], tree.root)
        print(f"  Receipt #{i} ({receipts[i]['type']}): {'✅ INCLUDED' if verified else '❌ MISSING'}")
    
    # Save checkpoint
    checkpoint_size = len(tree.leaves)
    checkpoint_root = tree.root
    
    # Add more receipts
    tree.append({"contract_id": "tc4", "type": "x402_payment", "timestamp": "2026-02-25T10:00:00Z", "sequence": 5})
    
    # Consistency check
    print("\n--- Consistency Check (old tree is prefix?) ---")
    check = tree.consistency_check(checkpoint_size, checkpoint_root)
    print(f"  Old size: {check['old_size']}, Current: {check['current_size']}")
    print(f"  Consistent: {'✅' if check['consistent'] else '❌'} — {check['reason']}")
    
    # Tamper detection
    print("\n--- Tamper Detection ---")
    fake_root = sha256("tampered")
    tamper_check = tree.consistency_check(checkpoint_size, fake_root)
    print(f"  Fake checkpoint: {'✅' if tamper_check['consistent'] else '🚨 TAMPERING DETECTED'} — {tamper_check['reason']}")
    
    # Gap detection
    print("\n--- Gap Detection ---")
    gapped_receipts = [
        {"sequence": 0, "timestamp": "2026-02-24T10:00:00Z"},
        {"sequence": 1, "timestamp": "2026-02-24T12:00:00Z"},
        # sequence 2 and 3 missing!
        {"sequence": 4, "timestamp": "2026-02-24T14:00:00Z"},
        {"sequence": 5, "timestamp": "2026-02-27T10:00:00Z"},  # 68h gap
    ]
    gaps = detect_gaps(gapped_receipts)
    for gap in gaps:
        print(f"  {'🚨' if gap['severity'] == 'HIGH' else '⚠️'} {gap['type']}: {gap['note']}")
    
    print(f"\n--- Summary ---")
    print(f"Tree size: {len(tree.leaves)} receipts")
    print(f"Root hash: {tree.root}")
    print(f"Gaps detected: {len(gaps)}")
    print(f"Pattern: RFC 6962 Certificate Transparency → Agent Receipt Transparency")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        tree = MerkleTree()
        for r in data.get("receipts", []):
            result = tree.append(r)
        gaps = detect_gaps(data.get("receipts", []))
        print(json.dumps({
            "tree_size": len(tree.leaves),
            "root_hash": tree.root,
            "gaps": gaps,
            "gap_count": len(gaps),
        }, indent=2))
    else:
        demo()
