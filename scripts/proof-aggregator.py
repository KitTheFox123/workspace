#!/usr/bin/env python3
"""
proof-aggregator.py — Aggregate independent proof layers into a single confidence score.

Takes N independent receipts (x402 on-chain, generation sig, DKIM email, attestation chain)
and outputs a compound confidence score based on:
1. Layer independence (are proofs from different systems?)
2. Temporal coherence (do timestamps align within expected windows?)
3. Diversity weighting (more independent layers = non-linear confidence boost)

Usage:
    python3 proof-aggregator.py demo          # Run with synthetic proofs
    python3 proof-aggregator.py score FILE    # Score a JSON proof bundle
"""

import hashlib
import json
import math
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional
from enum import Enum


class ProofType(str, Enum):
    X402_RECEIPT = "x402_receipt"         # On-chain transaction (Base/USDC)
    GENERATION_SIG = "generation_sig"     # Cryptographic signature from generator
    DKIM_ATTESTATION = "dkim_attestation" # Email with X-Claim-Hash in DKIM scope
    ATTESTATION_CHAIN = "attestation_chain"  # Isnad-style attestation
    KEY_ROTATION = "key_rotation"         # KERI-style pre-rotation proof
    WITNESS_SIG = "witness_sig"           # Third-party witness signature


# Which systems each proof type depends on (for independence calculation)
PROOF_SYSTEMS = {
    ProofType.X402_RECEIPT: {"blockchain", "wallet"},
    ProofType.GENERATION_SIG: {"signing_infra", "key_management"},
    ProofType.DKIM_ATTESTATION: {"email_provider", "dns"},
    ProofType.ATTESTATION_CHAIN: {"attestation_network", "key_management"},
    ProofType.KEY_ROTATION: {"key_management", "event_log"},
    ProofType.WITNESS_SIG: {"witness_infra", "key_management"},
}


@dataclass
class Proof:
    """A single proof layer."""
    proof_type: ProofType
    timestamp: str              # ISO timestamp
    source_agent: str           # DID or identifier of proof source
    evidence_hash: str          # SHA-256 of the evidence
    verified: bool = False      # Has this proof been locally verified?
    metadata: dict = field(default_factory=dict)

    @property
    def dt(self) -> datetime:
        return datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))


@dataclass
class AggregationResult:
    """Result of aggregating multiple proofs."""
    confidence: float           # 0.0 to 1.0
    layer_count: int
    independence_score: float   # How independent are the proof systems?
    temporal_coherence: float   # Do timestamps align?
    diversity_bonus: float      # Non-linear bonus for diverse proofs
    warnings: list = field(default_factory=list)
    details: dict = field(default_factory=dict)


class ProofAggregator:
    """Aggregates independent proof layers into compound confidence."""
    
    def __init__(self, max_temporal_drift_minutes: int = 60):
        self.max_drift = timedelta(minutes=max_temporal_drift_minutes)
    
    def score(self, proofs: list[Proof]) -> AggregationResult:
        """Score a bundle of proofs."""
        if not proofs:
            return AggregationResult(
                confidence=0.0, layer_count=0,
                independence_score=0.0, temporal_coherence=0.0,
                diversity_bonus=0.0, warnings=["No proofs provided"]
            )
        
        warnings = []
        
        # 1. Layer independence: how many distinct systems are involved?
        all_systems = set()
        per_proof_systems = []
        for p in proofs:
            systems = PROOF_SYSTEMS.get(p.proof_type, {"unknown"})
            per_proof_systems.append(systems)
            all_systems.update(systems)
        
        # Independence = unique systems / total system references
        total_refs = sum(len(s) for s in per_proof_systems)
        independence = len(all_systems) / total_refs if total_refs > 0 else 0
        
        # Check for shared key_management (common dependency)
        km_count = sum(1 for s in per_proof_systems if "key_management" in s)
        if km_count > 1:
            warnings.append(
                f"key_management shared across {km_count} proof types — "
                "compromise of signing infra affects multiple layers"
            )
            independence *= 0.85  # Penalty for shared dependency
        
        # 2. Temporal coherence: are timestamps within expected drift?
        timestamps = [p.dt for p in proofs]
        min_t, max_t = min(timestamps), max(timestamps)
        drift = max_t - min_t
        
        if drift <= self.max_drift:
            temporal = 1.0
        elif drift <= self.max_drift * 3:
            temporal = 0.7
            warnings.append(f"Temporal drift {drift} exceeds expected window")
        else:
            temporal = 0.3
            warnings.append(f"Large temporal drift {drift} — proofs may not relate to same event")
        
        # 3. Diversity bonus: non-linear confidence from independent layers
        # Based on: each independent proof raises attacker cost non-linearly
        unique_types = len(set(p.proof_type for p in proofs))
        # Sigmoid-like: diminishing returns after 3-4 layers
        diversity = 1 - math.exp(-0.7 * unique_types)
        
        # 4. Verification status
        verified_count = sum(1 for p in proofs if p.verified)
        verification_ratio = verified_count / len(proofs)
        if verification_ratio < 1.0:
            warnings.append(
                f"Only {verified_count}/{len(proofs)} proofs locally verified"
            )
        
        # 5. Source diversity: different agents providing proofs?
        unique_sources = len(set(p.source_agent for p in proofs))
        source_diversity = min(unique_sources / max(len(proofs), 1), 1.0)
        if unique_sources == 1:
            warnings.append("All proofs from same source — no independent attestation")
            source_diversity = 0.3
        
        # Compound score
        # Weighted: independence 30%, temporal 20%, diversity 25%, verification 15%, source 10%
        raw = (
            0.30 * independence +
            0.20 * temporal +
            0.25 * diversity +
            0.15 * verification_ratio +
            0.10 * source_diversity
        )
        
        # Clamp to [0, 1]
        confidence = max(0.0, min(1.0, raw))
        
        return AggregationResult(
            confidence=round(confidence, 4),
            layer_count=len(proofs),
            independence_score=round(independence, 4),
            temporal_coherence=round(temporal, 4),
            diversity_bonus=round(diversity, 4),
            warnings=warnings,
            details={
                "unique_proof_types": unique_types,
                "unique_systems": len(all_systems),
                "unique_sources": unique_sources,
                "verified_ratio": round(verification_ratio, 2),
                "temporal_drift": str(drift),
                "source_diversity": round(source_diversity, 4),
            }
        )
    
    def compare_bundles(self, bundles: dict[str, list[Proof]]) -> dict:
        """Compare multiple proof bundles (e.g., for different transactions)."""
        results = {}
        for name, proofs in bundles.items():
            results[name] = asdict(self.score(proofs))
        return results


def demo():
    """Demo with synthetic proof bundles."""
    print("=" * 60)
    print("Proof Aggregator — Compound Confidence Scoring")
    print("=" * 60)
    
    now = datetime.now(timezone.utc)
    
    # Bundle 1: Strong — 3 independent layers, different sources
    strong_bundle = [
        Proof(
            proof_type=ProofType.X402_RECEIPT,
            timestamp=(now - timedelta(minutes=5)).isoformat(),
            source_agent="agent:gendolf",
            evidence_hash=hashlib.sha256(b"tx:0x1234").hexdigest(),
            verified=True,
            metadata={"chain": "base", "amount": "0.01 SOL"}
        ),
        Proof(
            proof_type=ProofType.GENERATION_SIG,
            timestamp=(now - timedelta(minutes=3)).isoformat(),
            source_agent="agent:kit_fox",
            evidence_hash=hashlib.sha256(b"deliverable:tc3").hexdigest(),
            verified=True,
        ),
        Proof(
            proof_type=ProofType.DKIM_ATTESTATION,
            timestamp=(now - timedelta(minutes=1)).isoformat(),
            source_agent="agent:bro_agent",
            evidence_hash=hashlib.sha256(b"judgment:0.92").hexdigest(),
            verified=True,
            metadata={"x_claim_hash": "sha256:abc123"}
        ),
    ]
    
    # Bundle 2: Weak — single source, no verification
    weak_bundle = [
        Proof(
            proof_type=ProofType.ATTESTATION_CHAIN,
            timestamp=now.isoformat(),
            source_agent="agent:unknown",
            evidence_hash=hashlib.sha256(b"self-attest").hexdigest(),
            verified=False,
        ),
    ]
    
    # Bundle 3: Medium — two layers but shared key_management
    medium_bundle = [
        Proof(
            proof_type=ProofType.GENERATION_SIG,
            timestamp=(now - timedelta(minutes=10)).isoformat(),
            source_agent="agent:alice",
            evidence_hash=hashlib.sha256(b"sig1").hexdigest(),
            verified=True,
        ),
        Proof(
            proof_type=ProofType.ATTESTATION_CHAIN,
            timestamp=(now - timedelta(minutes=8)).isoformat(),
            source_agent="agent:bob",
            evidence_hash=hashlib.sha256(b"attest1").hexdigest(),
            verified=True,
        ),
    ]
    
    # Bundle 4: Suspicious — good layers but huge temporal drift
    suspicious_bundle = [
        Proof(
            proof_type=ProofType.X402_RECEIPT,
            timestamp=(now - timedelta(hours=48)).isoformat(),
            source_agent="agent:old_tx",
            evidence_hash=hashlib.sha256(b"old").hexdigest(),
            verified=True,
        ),
        Proof(
            proof_type=ProofType.DKIM_ATTESTATION,
            timestamp=now.isoformat(),
            source_agent="agent:fresh_email",
            evidence_hash=hashlib.sha256(b"new").hexdigest(),
            verified=True,
        ),
    ]
    
    agg = ProofAggregator()
    
    bundles = {
        "tc3_strong (3 layers, 3 sources)": strong_bundle,
        "self_attest_weak (1 layer, unverified)": weak_bundle,
        "medium (2 layers, shared km)": medium_bundle,
        "suspicious (48h drift)": suspicious_bundle,
    }
    
    for name, proofs in bundles.items():
        print(f"\n--- {name} ---")
        result = agg.score(proofs)
        confidence_bar = "█" * int(result.confidence * 20) + "░" * (20 - int(result.confidence * 20))
        print(f"  Confidence: [{confidence_bar}] {result.confidence:.1%}")
        print(f"  Layers: {result.layer_count} | Independence: {result.independence_score:.2f} | "
              f"Temporal: {result.temporal_coherence:.2f} | Diversity: {result.diversity_bonus:.2f}")
        if result.warnings:
            for w in result.warnings:
                print(f"  ⚠️  {w}")
        print(f"  Details: {json.dumps(result.details, indent=4)}")
    
    # Save comparison
    comparison = agg.compare_bundles(bundles)
    with open("proof-aggregation-demo.json", "w") as f:
        json.dump(comparison, f, indent=2, default=str)
    print(f"\nResults saved to proof-aggregation-demo.json")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "score" and len(sys.argv) > 2:
        with open(sys.argv[2]) as f:
            data = json.load(f)
        proofs = [Proof(**p) for p in data]
        result = ProofAggregator().score(proofs)
        print(json.dumps(asdict(result), indent=2, default=str))
    else:
        print(__doc__)
