#!/usr/bin/env python3
"""
inclusion-proof-server.py — Who serves Merkle inclusion proofs?

Per gendolf (2026-03-17): "who serves the inclusion proofs? 
centralized log or distributed witnesses?"

CT answer: multiple independent logs (Google, DigiCert, Sectigo).
Split-view detection = query ≥2 logs.

L3.5 answer: any witness can serve proofs. Decentralized by default.
The receipt carries the root. The proof is derivable from any copy of the tree.

This script models 3 architectures and compares:
1. Centralized log (single operator)
2. Federated logs (CT model — N independent operators)
3. Witness-served (any attester serves proofs from their tree copy)

Usage: python3 inclusion-proof-server.py
"""

import json
import hashlib
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def merkle_root(leaves: List[str]) -> str:
    if not leaves:
        return sha256("empty")
    layer = [sha256(l) for l in leaves]
    while len(layer) > 1:
        next_layer = []
        for i in range(0, len(layer), 2):
            if i + 1 < len(layer):
                next_layer.append(sha256(layer[i] + layer[i+1]))
            else:
                next_layer.append(layer[i])
        layer = next_layer
    return layer[0]


def merkle_proof(leaves: List[str], index: int) -> List[Dict]:
    """Generate inclusion proof for leaf at index."""
    hashes = [sha256(l) for l in leaves]
    proof = []
    while len(hashes) > 1:
        next_hashes = []
        for i in range(0, len(hashes), 2):
            if i + 1 < len(hashes):
                if i == index or i + 1 == index:
                    sibling_idx = i + 1 if i == index else i
                    proof.append({
                        "hash": hashes[sibling_idx],
                        "position": "right" if sibling_idx > index else "left"
                    })
                next_hashes.append(sha256(hashes[i] + hashes[i+1]))
            else:
                next_hashes.append(hashes[i])
        index //= 2
        hashes = next_hashes
    return proof


@dataclass
class ProofServer:
    name: str
    operator: str
    architecture: str  # centralized | federated | witness
    availability: float = 0.99
    latency_ms: float = 50.0
    honest: bool = True
    
    def serve_proof(self, receipt_id: str, tree_leaves: List[str]) -> Optional[Dict]:
        """Attempt to serve an inclusion proof."""
        if random.random() > self.availability:
            return None  # server down
        
        if not self.honest:
            # Split-view attack: return valid-looking but wrong proof
            return {"proof": [{"hash": sha256("fake"), "position": "right"}], "tampered": True}
        
        # Find receipt in tree
        for i, leaf in enumerate(tree_leaves):
            if sha256(leaf) == receipt_id or leaf == receipt_id:
                return {
                    "proof": merkle_proof(tree_leaves, i),
                    "root": merkle_root(tree_leaves),
                    "server": self.name,
                    "tampered": False,
                }
        return None


@dataclass
class Architecture:
    name: str
    servers: List[ProofServer]
    min_agreement: int = 1  # how many servers must agree
    
    def query(self, receipt_id: str, tree_leaves: List[str]) -> Dict:
        """Query architecture for inclusion proof."""
        results = []
        for server in self.servers:
            result = server.serve_proof(receipt_id, tree_leaves)
            if result:
                results.append(result)
        
        if len(results) < self.min_agreement:
            return {"status": "UNAVAILABLE", "responses": len(results), "needed": self.min_agreement}
        
        # Check agreement (split-view detection)
        roots = set(r.get("root", "") for r in results if not r.get("tampered"))
        tampered = [r for r in results if r.get("tampered")]
        
        if len(roots) > 1:
            return {"status": "SPLIT_VIEW_DETECTED", "distinct_roots": len(roots), "servers": len(results)}
        
        if tampered and results:
            # Mix of honest and dishonest
            honest_roots = set(r["root"] for r in results if not r["tampered"])
            if honest_roots:
                return {"status": "TAMPER_DETECTED", "honest_servers": len(results) - len(tampered)}
        
        return {
            "status": "VERIFIED",
            "root": results[0].get("root"),
            "proof": results[0].get("proof"),
            "agreement": len(results),
            "servers_queried": len(self.servers),
        }


def demo():
    # Simulate 100 receipts
    receipts = [f"receipt_{i}" for i in range(100)]
    
    # Three architectures
    centralized = Architecture("Centralized (single log)", [
        ProofServer("PayLock-Log", "paylock", "centralized", availability=0.995, latency_ms=20),
    ], min_agreement=1)
    
    federated = Architecture("Federated (CT model)", [
        ProofServer("Log-Alpha", "org:alpha", "federated", availability=0.99, latency_ms=50),
        ProofServer("Log-Beta", "org:beta", "federated", availability=0.98, latency_ms=60),
        ProofServer("Log-Gamma", "org:gamma", "federated", availability=0.97, latency_ms=45),
    ], min_agreement=2)
    
    witness_served = Architecture("Witness-served (L3.5)", [
        ProofServer("Witness-1", "org:alpha", "witness", availability=0.95, latency_ms=80),
        ProofServer("Witness-2", "org:beta", "witness", availability=0.93, latency_ms=90),
        ProofServer("Witness-3", "org:gamma", "witness", availability=0.90, latency_ms=100),
    ], min_agreement=2)
    
    # Attack scenario: one dishonest server
    federated_attack = Architecture("Federated + 1 dishonest", [
        ProofServer("Log-Alpha", "org:alpha", "federated", availability=0.99, honest=True),
        ProofServer("Log-Evil", "org:evil", "federated", availability=0.99, honest=False),
        ProofServer("Log-Gamma", "org:gamma", "federated", availability=0.97, honest=True),
    ], min_agreement=2)
    
    print("=" * 60)
    print("INCLUSION PROOF SERVER ARCHITECTURES")
    print("Who serves the proofs? (gendolf, 2026-03-17)")
    print("=" * 60)
    
    architectures = [centralized, federated, witness_served, federated_attack]
    
    for arch in architectures:
        verified = 0
        unavailable = 0
        split_view = 0
        tamper = 0
        
        for receipt in receipts:
            result = arch.query(sha256(receipt), receipts)
            if result["status"] == "VERIFIED": verified += 1
            elif result["status"] == "UNAVAILABLE": unavailable += 1
            elif result["status"] == "SPLIT_VIEW_DETECTED": split_view += 1
            elif result["status"] == "TAMPER_DETECTED": tamper += 1
        
        print(f"\n--- {arch.name} ---")
        print(f"  Servers: {len(arch.servers)}, Min agreement: {arch.min_agreement}")
        print(f"  Verified: {verified}%")
        print(f"  Unavailable: {unavailable}%")
        print(f"  Split-view: {split_view}%")
        print(f"  Tamper detected: {tamper}%")
    
    print(f"\n{'=' * 60}")
    print("TRADEOFFS")
    print(f"{'=' * 60}")
    print("""
  Centralized:  Fastest, simplest. Single point of failure + trust.
                If PayLock lies, nobody knows.
  
  Federated:    CT model. ≥2 independent logs detect split-view.
                Requires infrastructure investment per log operator.
  
  Witness-served: Each attester serves proofs from their tree copy.
                  No dedicated log infrastructure. Lower availability
                  per server but redundancy compensates.
                  
  L3.5 recommendation: START witness-served (zero infra cost),
  MIGRATE to federated when volume justifies dedicated logs.
  
  The receipt carries the root. The proof is derivable from any
  copy of the tree. Centralization is a deployment choice, not
  a protocol requirement.
""")


if __name__ == '__main__':
    demo()
