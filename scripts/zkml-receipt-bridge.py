#!/usr/bin/env python3
"""
zkml-receipt-bridge.py — Bridge zkML proofs to L3.5 receipt format
Maps clawproof receipts into receipt-format-minimal v0.2.1 schema.

Inspired by clawproof skill drop (moltbook 2026-03-18).
zkML proofs = cryptographic evidence of ML inference without re-running model.
"""

import json
import hashlib
import time
from dataclasses import dataclass, asdict

@dataclass
class ZkMLProof:
    """A zkML proof receipt from clawproof."""
    model_id: str
    model_hash: str
    input_hash: str
    output_hash: str
    proof_hash: str
    verification_time_ms: float
    receipt_id: str

@dataclass 
class L35Receipt:
    """L3.5 receipt-format-minimal v0.2.1."""
    v: str  # version
    ts: int  # timestamp
    src: str  # source agent
    dst: str  # destination/verifier
    act: str  # action type
    out: str  # outcome
    wit: list  # witnesses
    dims: dict  # trust dimensions
    dhash: str  # delivery hash
    seq: int | None = None  # sequence_id (optional, ADV-020)
    ext: dict | None = None  # extensions

def bridge_zkml_to_l35(proof: ZkMLProof, agent_id: str, verifier_id: str) -> L35Receipt:
    """Convert a zkML proof into an L3.5 receipt."""
    
    # Compute delivery hash from proof components
    delivery_content = f"{proof.model_hash}:{proof.input_hash}:{proof.output_hash}:{proof.proof_hash}"
    dhash = hashlib.sha256(delivery_content.encode()).hexdigest()[:16]
    
    # Trust dimensions derived from proof properties
    dims = {
        "groundedness": 1.0,  # zkML proof IS the ground truth
        "timeliness": 1.0 if proof.verification_time_ms < 100 else 0.8,
        "self_knowledge": None,  # not applicable to ML inference
        "provenance": 1.0,  # model hash proves provenance
        "verifiability": 1.0,  # that's the whole point of zkML
    }
    
    # Extension field carries zkML-specific data
    ext = {
        "zkml": {
            "model_hash": proof.model_hash,
            "input_hash": proof.input_hash,
            "output_hash": proof.output_hash,
            "proof_hash": proof.proof_hash,
            "verification_ms": proof.verification_time_ms,
            "receipt_id": proof.receipt_id,
        }
    }
    
    return L35Receipt(
        v="0.2.1",
        ts=int(time.time()),
        src=agent_id,
        dst=verifier_id,
        act="ml_inference",
        out="verified",
        wit=[f"zkml:{proof.model_id}"],
        dims=dims,
        dhash=dhash,
        ext=ext,
    )


def analyze_trust_properties(proof: ZkMLProof) -> dict:
    """Analyze what trust properties zkML proofs provide vs. L3.5 receipts."""
    return {
        "proof_provides": {
            "computational_integrity": True,   # model actually ran this input → output
            "model_provenance": True,          # which model (hash)
            "input_binding": True,             # proof bound to specific input
            "output_binding": True,            # proof bound to specific output
            "third_party_verifiable": True,    # anyone can verify without model weights
            "non_repudiation": True,           # can't deny making the inference
        },
        "receipt_adds": {
            "behavioral_context": True,        # this inference in context of history
            "witness_diversity": True,         # multiple independent verifiers
            "graduated_trust": True,           # trust level changes over time
            "delegation_chain": True,          # who asked for this inference
            "consequence_assessment": True,    # blast radius of the decision
            "temporal_continuity": True,       # MEMORY-CHAIN linkage
        },
        "combined_value": "zkML proves WHAT happened. L3.5 receipts prove WHY it matters.",
        "analogy": "zkML is the DNA test. Receipt is the court record. Both needed for justice."
    }


def main():
    # Demo: simulate a zkML proof
    proof = ZkMLProof(
        model_id="authorization",
        model_hash="sha256:a1b2c3d4e5f6",
        input_hash="sha256:1234567890ab",
        output_hash="sha256:fedcba987654",
        proof_hash="sha256:proof_deadbeef",
        verification_time_ms=80.0,
        receipt_id="demo-receipt-001",
    )
    
    receipt = bridge_zkml_to_l35(proof, "agent:kit_fox", "agent:verifier_01")
    
    print("=" * 60)
    print("zkML → L3.5 Receipt Bridge")
    print("=" * 60)
    
    print("\n📥 zkML Proof:")
    print(json.dumps(asdict(proof), indent=2))
    
    print("\n📤 L3.5 Receipt:")
    receipt_dict = asdict(receipt)
    receipt_dict = {k: v for k, v in receipt_dict.items() if v is not None}
    print(json.dumps(receipt_dict, indent=2))
    
    print("\n🔍 Trust Property Analysis:")
    analysis = analyze_trust_properties(proof)
    print(f"\n  zkML proves ({sum(analysis['proof_provides'].values())} properties):")
    for prop, val in analysis['proof_provides'].items():
        print(f"    ✓ {prop}")
    print(f"\n  L3.5 adds ({sum(analysis['receipt_adds'].values())} properties):")
    for prop, val in analysis['receipt_adds'].items():
        print(f"    + {prop}")
    
    print(f"\n  💡 {analysis['combined_value']}")
    print(f"  🧬 {analysis['analogy']}")
    
    # Wire size comparison
    receipt_json = json.dumps(receipt_dict, separators=(',', ':'))
    print(f"\n  📏 Wire size: {len(receipt_json)} bytes (with zkML extension)")
    
    # Without extension
    receipt_dict.pop('ext', None)
    minimal_json = json.dumps(receipt_dict, separators=(',', ':'))
    print(f"  📏 Minimal size: {len(minimal_json)} bytes (without extension)")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
