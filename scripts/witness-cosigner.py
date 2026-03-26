#!/usr/bin/env python3
"""
witness-cosigner.py — Transparency log witness protocol for ATF attestation checkpoints.

Maps the C2SP tlog-witness protocol (Jan 2026) + ArmoredWitness network to ATF.
Witnesses cosign attestation checkpoints after verifying consistency proofs,
providing append-only guarantees without trusting any single party.

Sources:
- C2SP tlog-witness.md (https://github.com/C2SP/C2SP/blob/main/tlog-witness.md)
- ArmoredWitness: 15 devices deployed globally (transparency.dev, Nov 2025)
- RFC 9162: Certificate Transparency v2.0
- Gossip protocol: arxiv 2011.04551

Key concepts:
- Witness cosigns checkpoints consistent with previously signed ones
- Single witness proves append-only; quorum (N-of-M) proves global consistency
- Witnesses don't validate leaf contents — that's for auditors/monitors
- Self-hosted git = self-attestation (santaclawd). Public witness = real evidence.

ATF mapping:
- Checkpoint = attestation batch summary (tree size + root hash)
- Consistency proof = Merkle proof that old tree is prefix of new tree
- Cosignature = witness endorsement of checkpoint
- Split-view attack = registry showing different states to different agents
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
from enum import Enum


class WitnessVerdict(Enum):
    """Witness verification outcomes."""
    COSIGNED = "cosigned"           # Checkpoint consistent, cosigned
    CONFLICT = "conflict"           # Old size doesn't match stored state
    INVALID_PROOF = "invalid_proof"  # Consistency proof failed
    UNKNOWN_ORIGIN = "unknown_origin"  # Log/registry not in witness config
    ROLLBACK = "rollback"           # Tree size decreased (critical!)


@dataclass
class Checkpoint:
    """
    Attestation checkpoint — summary of tree state.
    Maps to C2SP tlog-checkpoint format.
    """
    origin: str          # Registry identifier (e.g., "registry_alpha")
    tree_size: int       # Number of attestations in the tree
    root_hash: str       # Merkle root of all attestations
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signatures: list[dict] = field(default_factory=list)
    
    @property
    def checkpoint_id(self) -> str:
        """Deterministic ID from origin + size + root."""
        data = f"{self.origin}:{self.tree_size}:{self.root_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass 
class Cosignature:
    """
    Witness cosignature on a checkpoint.
    Maps to C2SP tlog-cosignature format.
    """
    witness_id: str
    checkpoint_id: str
    origin: str
    tree_size: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signature: str = ""  # Ed25519 signature (simulated)
    
    def __post_init__(self):
        if not self.signature:
            # Simulate signature
            data = f"{self.witness_id}:{self.checkpoint_id}:{self.tree_size}"
            self.signature = hashlib.sha256(data.encode()).hexdigest()[:32]


@dataclass
class ConsistencyProof:
    """Merkle consistency proof that old tree is prefix of new tree."""
    old_size: int
    new_size: int
    proof_hashes: list[str]
    
    def verify(self, old_root: str, new_root: str) -> bool:
        """
        Verify consistency proof.
        Simplified: in production, this is RFC 6962 Section 2.1.2.
        Here we simulate verification based on size ordering + hash chain.
        """
        if self.old_size > self.new_size:
            return False
        if self.old_size == 0:
            return True  # Empty tree is consistent with everything
        if self.old_size == self.new_size:
            return old_root == new_root
        # Simulate: verify proof hashes chain correctly
        # In production: Merkle consistency proof verification
        expected_proof_length = max(1, (self.new_size - self.old_size).bit_length())
        return len(self.proof_hashes) <= expected_proof_length + 2


class Witness:
    """
    Transparency log witness for ATF attestation registries.
    
    Per C2SP tlog-witness protocol:
    - Tracks latest checkpoint per origin (registry)
    - Cosigns new checkpoints only after verifying consistency
    - Detects rollbacks, split views, and inconsistent trees
    - Does NOT validate attestation contents (that's for auditors)
    """
    
    def __init__(self, witness_id: str, trusted_origins: list[str]):
        self.witness_id = witness_id
        self.trusted_origins = set(trusted_origins)
        # Latest cosigned checkpoint per origin
        self.state: dict[str, Checkpoint] = {}
        self.cosignature_log: list[Cosignature] = []
        self.incident_log: list[dict] = []
    
    def process_checkpoint(
        self, 
        checkpoint: Checkpoint, 
        proof: ConsistencyProof
    ) -> tuple[WitnessVerdict, Optional[Cosignature]]:
        """
        Process a new checkpoint submission.
        
        Per C2SP protocol:
        1. Verify origin is known → 404 if not
        2. Verify checkpoint signature → 403 if invalid
        3. Check old_size matches stored state → 409 if mismatch
        4. Verify consistency proof → 422 if invalid
        5. Persist + cosign → 200
        """
        # Step 1: Check origin
        if checkpoint.origin not in self.trusted_origins:
            self.incident_log.append({
                "type": "unknown_origin",
                "origin": checkpoint.origin,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return WitnessVerdict.UNKNOWN_ORIGIN, None
        
        # Step 2: (Signature verification simulated — in production, Ed25519)
        
        # Step 3: Check old_size matches stored state
        stored = self.state.get(checkpoint.origin)
        stored_size = stored.tree_size if stored else 0
        stored_root = stored.root_hash if stored else ""
        
        if proof.old_size != stored_size:
            self.incident_log.append({
                "type": "conflict",
                "origin": checkpoint.origin,
                "expected_old_size": stored_size,
                "got_old_size": proof.old_size,
                "message": f"Old size mismatch: expected {stored_size}, got {proof.old_size}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return WitnessVerdict.CONFLICT, None
        
        # Detect rollback (tree size decrease)
        if checkpoint.tree_size < stored_size:
            self.incident_log.append({
                "type": "ROLLBACK",
                "origin": checkpoint.origin,
                "stored_size": stored_size,
                "new_size": checkpoint.tree_size,
                "severity": "CRITICAL",
                "message": f"Tree size DECREASED from {stored_size} to {checkpoint.tree_size}!",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return WitnessVerdict.ROLLBACK, None
        
        # Step 4: Verify consistency proof
        if not proof.verify(stored_root, checkpoint.root_hash):
            self.incident_log.append({
                "type": "invalid_proof",
                "origin": checkpoint.origin,
                "old_size": proof.old_size,
                "new_size": proof.new_size,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return WitnessVerdict.INVALID_PROOF, None
        
        # Step 5: Persist and cosign (atomically per spec)
        self.state[checkpoint.origin] = checkpoint
        cosig = Cosignature(
            witness_id=self.witness_id,
            checkpoint_id=checkpoint.checkpoint_id,
            origin=checkpoint.origin,
            tree_size=checkpoint.tree_size,
        )
        self.cosignature_log.append(cosig)
        
        return WitnessVerdict.COSIGNED, cosig


class WitnessNetwork:
    """
    Network of witnesses providing quorum-based global consistency.
    
    Per ArmoredWitness design:
    - N-of-M quorum for global consistency
    - Single witness sufficient for append-only proof
    - Diverse custodians reduce coercion risk
    """
    
    def __init__(self, quorum_size: int):
        self.witnesses: dict[str, Witness] = {}
        self.quorum_size = quorum_size
    
    def add_witness(self, witness: Witness):
        self.witnesses[witness.witness_id] = witness
    
    def submit_checkpoint(
        self, 
        checkpoint: Checkpoint, 
        proof: ConsistencyProof
    ) -> dict:
        """Submit checkpoint to all witnesses, collect cosignatures."""
        results = {}
        cosignatures = []
        
        for wid, witness in self.witnesses.items():
            verdict, cosig = witness.process_checkpoint(checkpoint, proof)
            results[wid] = verdict.value
            if cosig:
                cosignatures.append(cosig)
        
        quorum_met = len(cosignatures) >= self.quorum_size
        
        return {
            "origin": checkpoint.origin,
            "tree_size": checkpoint.tree_size,
            "checkpoint_id": checkpoint.checkpoint_id,
            "witness_results": results,
            "cosignatures_collected": len(cosignatures),
            "quorum_required": self.quorum_size,
            "quorum_met": quorum_met,
            "globally_consistent": quorum_met,
            "cosignatures": [
                {"witness": c.witness_id, "signature": c.signature[:16] + "..."}
                for c in cosignatures
            ],
        }


def run_scenarios():
    """Demonstrate witness cosigning for ATF attestation checkpoints."""
    print("=" * 70)
    print("WITNESS COSIGNER — ATF ATTESTATION CHECKPOINT VERIFICATION")
    print("Based on C2SP tlog-witness (Jan 2026) + ArmoredWitness")
    print("=" * 70)
    
    # Setup: 5 witnesses, quorum of 3 (N-of-M)
    trusted = ["registry_alpha", "registry_beta", "bridge_ab"]
    network = WitnessNetwork(quorum_size=3)
    
    for i in range(5):
        w = Witness(f"witness_{i}", trusted)
        network.add_witness(w)
    
    # Scenario 1: Normal checkpoint progression
    print("\n--- Scenario 1: Normal checkpoint (first submission) ---")
    cp1 = Checkpoint("registry_alpha", tree_size=100, root_hash="aabbcc")
    proof1 = ConsistencyProof(old_size=0, new_size=100, proof_hashes=[])
    result = network.submit_checkpoint(cp1, proof1)
    print(json.dumps(result, indent=2))
    
    # Scenario 2: Consistent update
    print("\n--- Scenario 2: Consistent update (100 → 200) ---")
    cp2 = Checkpoint("registry_alpha", tree_size=200, root_hash="ddeeff")
    proof2 = ConsistencyProof(old_size=100, new_size=200, proof_hashes=["hash1"])
    result = network.submit_checkpoint(cp2, proof2)
    print(json.dumps(result, indent=2))
    
    # Scenario 3: Split-view attempt (old_size doesn't match)
    print("\n--- Scenario 3: Split-view attack (wrong old_size) ---")
    cp3 = Checkpoint("registry_alpha", tree_size=250, root_hash="112233")
    proof3 = ConsistencyProof(old_size=150, new_size=250, proof_hashes=["hash2"])
    result = network.submit_checkpoint(cp3, proof3)
    print(json.dumps(result, indent=2))
    
    # Scenario 4: Rollback attempt
    print("\n--- Scenario 4: Rollback attempt (200 → 180) ---")
    cp4 = Checkpoint("registry_alpha", tree_size=180, root_hash="445566")
    proof4 = ConsistencyProof(old_size=200, new_size=180, proof_hashes=[])
    result = network.submit_checkpoint(cp4, proof4)
    print(json.dumps(result, indent=2))
    
    # Scenario 5: Unknown origin
    print("\n--- Scenario 5: Unknown registry ---")
    cp5 = Checkpoint("rogue_registry", tree_size=50, root_hash="999999")
    proof5 = ConsistencyProof(old_size=0, new_size=50, proof_hashes=[])
    result = network.submit_checkpoint(cp5, proof5)
    print(json.dumps(result, indent=2))
    
    # Print incident log from any witness
    w0 = list(network.witnesses.values())[0]
    if w0.incident_log:
        print(f"\n--- Witness {w0.witness_id} incident log ---")
        for incident in w0.incident_log:
            print(f"  [{incident['type'].upper()}] {incident.get('message', incident.get('origin', ''))}")
    
    print(f"\n{'=' * 70}")
    print("Key principles:")
    print("- Single witness = append-only proof (no rollbacks)")
    print("- N-of-M quorum = global consistency (no split views)")
    print("- Witnesses don't validate attestation CONTENTS — only tree structure")
    print("- Self-hosted git = self-attestation. Public witnesses = real evidence.")
    print("- 15 ArmoredWitness devices deployed globally (transparency.dev)")
    
    return True


if __name__ == "__main__":
    run_scenarios()
