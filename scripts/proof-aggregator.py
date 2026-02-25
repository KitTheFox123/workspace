#!/usr/bin/env python3
"""
proof-aggregator.py — N independent receipts → 1 confidence score.

Takes multiple attestation layers (x402 tx, DKIM signature, generation signature,
isnad attestation, PayLock escrow) and computes a compound confidence score.

The key insight: layers are valuable because they're INDEPENDENT failure modes.
Correlated attesters = expensive groupthink. Diverse proof types = real security.

Scoring model:
- Each proof type has a base weight (how hard to forge independently)
- Independence bonus: more diverse proof types → superlinear score
- Staleness penalty: older proofs decay
- Correlation penalty: proofs from same infrastructure reduce independence

Usage:
    python proof-aggregator.py demo
    python proof-aggregator.py verify receipts.json
    echo '{"proofs": [...]}' | python proof-aggregator.py -
"""

import json
import sys
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
from enum import Enum


class ProofType(str, Enum):
    X402_TX = "x402_tx"           # On-chain transaction receipt
    DKIM = "dkim"                 # DKIM-signed email header
    GENERATION_SIG = "gen_sig"    # Cryptographic signature at generation time
    ISNAD_ATTESTATION = "isnad"   # isnad chain attestation
    PAYLOCK_ESCROW = "paylock"    # PayLock escrow completion record
    CLAWTASK_COMPLETION = "clawtask"  # ClawTasks bounty completion
    WITNESS_SIG = "witness"       # Third-party witness signature


# Base weights: how hard is this proof type to forge independently?
# Scale: 0-1 where 1 = requires compromising independent infrastructure
PROOF_WEIGHTS = {
    ProofType.X402_TX: 0.9,          # On-chain, requires wallet compromise
    ProofType.DKIM: 0.7,             # Email infra, requires MTA compromise
    ProofType.GENERATION_SIG: 0.8,   # Key material, requires key theft
    ProofType.ISNAD_ATTESTATION: 0.6, # Attestation chain, requires colluding attesters
    ProofType.PAYLOCK_ESCROW: 0.85,  # Escrow + judgment, requires buyer+seller collusion
    ProofType.CLAWTASK_COMPLETION: 0.75,  # Platform + reviewer
    ProofType.WITNESS_SIG: 0.5,      # Single witness, weakest alone
}

# Infrastructure groups: proofs sharing infrastructure are correlated
INFRA_GROUPS = {
    ProofType.X402_TX: "blockchain",
    ProofType.DKIM: "email",
    ProofType.GENERATION_SIG: "agent_keys",
    ProofType.ISNAD_ATTESTATION: "attestation_network",
    ProofType.PAYLOCK_ESCROW: "blockchain",  # same chain as x402
    ProofType.CLAWTASK_COMPLETION: "platform",
    ProofType.WITNESS_SIG: "attestation_network",  # same as isnad
}


@dataclass
class Proof:
    """A single proof receipt."""
    proof_type: str              # ProofType value
    issuer: str                  # Who created this proof
    subject: str                 # What is being attested
    claim_hash: str              # Hash of the claim being proved
    timestamp: str               # ISO timestamp
    metadata: dict = field(default_factory=dict)  # Type-specific data
    # e.g., for x402: {tx_hash, chain, amount}
    # e.g., for dkim: {selector, domain, h_tag_includes}
    # e.g., for isnad: {attester_did, confidence}


@dataclass
class AggregateResult:
    """Result of proof aggregation."""
    confidence: float            # 0-1 compound score
    layer_count: int             # Number of distinct proof types
    independence_score: float    # How independent are the layers
    staleness_penalty: float     # Time decay factor
    correlation_penalty: float   # Infrastructure overlap penalty
    proofs_evaluated: int
    per_layer: dict              # Score breakdown by proof type
    grade: str                   # Human-readable grade
    warnings: list = field(default_factory=list)


def compute_staleness(timestamp_str: str, max_age_hours: float = 168) -> float:
    """Exponential decay based on proof age. 1.0 = fresh, 0.0 = expired."""
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_hours = (now - ts).total_seconds() / 3600
        if age_hours < 0:
            return 0.5  # Future timestamp = suspicious
        if age_hours > max_age_hours:
            return 0.1  # Very old but not zero
        # Half-life of 48 hours
        return math.exp(-0.693 * age_hours / 48)
    except (ValueError, TypeError):
        return 0.5  # Can't parse = uncertain


def compute_independence(proof_types: list[str]) -> float:
    """
    Compute independence score based on infrastructure diversity.
    More diverse infra groups = higher independence.
    """
    groups = set()
    for pt in proof_types:
        try:
            groups.add(INFRA_GROUPS[ProofType(pt)])
        except (ValueError, KeyError):
            groups.add(f"unknown_{pt}")
    
    n_proofs = len(proof_types)
    n_groups = len(groups)
    
    if n_proofs <= 1:
        return 0.5
    
    # Perfect independence: every proof in different group
    # Worst: all in same group
    ratio = n_groups / n_proofs
    # Superlinear bonus for diversity
    return min(1.0, ratio * (1 + 0.2 * (n_groups - 1)))


def compute_correlation_penalty(proof_types: list[str]) -> float:
    """Penalty for proofs sharing infrastructure. 0 = no penalty, 1 = full penalty."""
    groups = []
    for pt in proof_types:
        try:
            groups.append(INFRA_GROUPS[ProofType(pt)])
        except (ValueError, KeyError):
            groups.append(f"unknown_{pt}")
    
    if len(groups) <= 1:
        return 0.0
    
    # Count duplicates
    from collections import Counter
    counts = Counter(groups)
    duplicates = sum(c - 1 for c in counts.values())
    return duplicates / len(groups)


def aggregate(proofs: list[Proof]) -> AggregateResult:
    """
    Aggregate N independent proofs into a single confidence score.
    
    Model: P(all_forged) = product(1 - weight_i * freshness_i) * correlation_factor
    Confidence = 1 - P(all_forged), adjusted for independence
    """
    if not proofs:
        return AggregateResult(
            confidence=0.0, layer_count=0, independence_score=0.0,
            staleness_penalty=0.0, correlation_penalty=0.0,
            proofs_evaluated=0, per_layer={}, grade="F",
            warnings=["No proofs provided"]
        )
    
    warnings = []
    per_layer = {}
    proof_types = []
    
    # Check claim hash consistency
    claim_hashes = set(p.claim_hash for p in proofs)
    if len(claim_hashes) > 1:
        warnings.append(f"Multiple claim hashes detected: {claim_hashes}. Proofs may not refer to same claim.")
    
    # Compute per-proof scores
    survival_probs = []  # P(this proof is forged)
    for p in proofs:
        try:
            pt = ProofType(p.proof_type)
            weight = PROOF_WEIGHTS.get(pt, 0.3)
        except ValueError:
            weight = 0.3
            warnings.append(f"Unknown proof type: {p.proof_type}")
        
        freshness = compute_staleness(p.timestamp)
        effective_weight = weight * freshness
        
        per_layer[p.proof_type] = {
            "base_weight": weight,
            "freshness": round(freshness, 3),
            "effective_weight": round(effective_weight, 3),
            "issuer": p.issuer,
        }
        
        proof_types.append(p.proof_type)
        survival_probs.append(1 - effective_weight)
    
    # P(all forged) = product of individual forge probabilities
    p_all_forged = 1.0
    for sp in survival_probs:
        p_all_forged *= sp
    
    # Independence and correlation adjustments
    independence = compute_independence(proof_types)
    correlation = compute_correlation_penalty(proof_types)
    
    # Adjusted confidence
    # High independence amplifies compound effect
    # High correlation dampens it
    raw_confidence = 1 - p_all_forged
    adjusted = raw_confidence * (0.5 + 0.5 * independence) * (1 - 0.3 * correlation)
    confidence = min(1.0, max(0.0, adjusted))
    
    # Average staleness
    avg_staleness = 1.0 - sum(compute_staleness(p.timestamp) for p in proofs) / len(proofs)
    
    # Grade
    if confidence >= 0.95:
        grade = "A+"
    elif confidence >= 0.90:
        grade = "A"
    elif confidence >= 0.80:
        grade = "B"
    elif confidence >= 0.65:
        grade = "C"
    elif confidence >= 0.50:
        grade = "D"
    else:
        grade = "F"
    
    # Warnings
    if len(set(proof_types)) == 1:
        warnings.append("All proofs are same type — no independence benefit")
    if correlation > 0.5:
        warnings.append(f"High infrastructure correlation ({correlation:.1%}) — proofs may not be truly independent")
    if avg_staleness > 0.5:
        warnings.append("Proofs are getting stale — consider refreshing attestations")
    
    return AggregateResult(
        confidence=round(confidence, 4),
        layer_count=len(set(proof_types)),
        independence_score=round(independence, 3),
        staleness_penalty=round(avg_staleness, 3),
        correlation_penalty=round(correlation, 3),
        proofs_evaluated=len(proofs),
        per_layer=per_layer,
        grade=grade,
        warnings=warnings,
    )


def demo():
    """Demo with test case 3 scenario."""
    print("=" * 60)
    print("Proof Aggregator Demo — Test Case 3 Scenario")
    print("=" * 60)
    
    now = datetime.now(timezone.utc).isoformat()
    claim = "delivery:tc3:agent-economy-at-scale"
    claim_hash = "sha256:a1b2c3d4..."
    
    # Scenario 1: Full compound proof (what tc3 could have had)
    print("\n--- Scenario 1: Full compound (x402 + DKIM + isnad + PayLock) ---")
    proofs_full = [
        Proof(ProofType.X402_TX, "gendolf", claim, claim_hash, now,
              {"tx_hash": "0xabc...", "chain": "base", "amount": "0.01 SOL"}),
        Proof(ProofType.DKIM, "agentmail", claim, claim_hash, now,
              {"domain": "agentmail.to", "h_tag_includes": "X-Claim-Hash"}),
        Proof(ProofType.ISNAD_ATTESTATION, "bro_agent", claim, claim_hash, now,
              {"confidence": 0.92}),
        Proof(ProofType.PAYLOCK_ESCROW, "paylock", claim, claim_hash, now,
              {"escrow_id": "tc3", "status": "released"}),
    ]
    result1 = aggregate(proofs_full)
    print_result(result1)
    
    # Scenario 2: What tc3 actually had (isnad + PayLock only)
    print("\n--- Scenario 2: Actual tc3 (isnad + PayLock) ---")
    proofs_actual = [
        Proof(ProofType.ISNAD_ATTESTATION, "bro_agent", claim, claim_hash, now,
              {"confidence": 0.92}),
        Proof(ProofType.PAYLOCK_ESCROW, "paylock", claim, claim_hash, now,
              {"escrow_id": "tc3", "status": "released"}),
    ]
    result2 = aggregate(proofs_actual)
    print_result(result2)
    
    # Scenario 3: Sybil attack — 5 witnesses, all same infra
    print("\n--- Scenario 3: Sybil — 5 witnesses (same infra group) ---")
    proofs_sybil = [
        Proof(ProofType.WITNESS_SIG, f"witness_{i}", claim, claim_hash, now)
        for i in range(5)
    ]
    result3 = aggregate(proofs_sybil)
    print_result(result3)
    
    # Scenario 4: Single strong proof
    print("\n--- Scenario 4: Single x402 transaction ---")
    proofs_single = [
        Proof(ProofType.X402_TX, "gendolf", claim, claim_hash, now,
              {"tx_hash": "0xabc...", "chain": "base"}),
    ]
    result4 = aggregate(proofs_single)
    print_result(result4)
    
    # Scenario 5: Stale proofs
    print("\n--- Scenario 5: Week-old proofs (stale) ---")
    old_time = "2026-02-18T03:00:00Z"
    proofs_stale = [
        Proof(ProofType.X402_TX, "gendolf", claim, claim_hash, old_time),
        Proof(ProofType.DKIM, "agentmail", claim, claim_hash, old_time),
        Proof(ProofType.ISNAD_ATTESTATION, "bro_agent", claim, claim_hash, old_time),
    ]
    result5 = aggregate(proofs_stale)
    print_result(result5)


def print_result(result: AggregateResult):
    """Pretty-print an aggregate result."""
    print(f"  Grade: {result.grade} ({result.confidence:.1%} confidence)")
    print(f"  Layers: {result.layer_count} types, {result.proofs_evaluated} proofs")
    print(f"  Independence: {result.independence_score:.1%}")
    print(f"  Correlation penalty: {result.correlation_penalty:.1%}")
    print(f"  Staleness penalty: {result.staleness_penalty:.1%}")
    for pt, info in result.per_layer.items():
        print(f"    {pt}: weight={info['effective_weight']:.2f} "
              f"(base={info['base_weight']:.1f} × fresh={info['freshness']:.2f}) "
              f"from {info['issuer']}")
    for w in result.warnings:
        print(f"  ⚠️  {w}")


def verify_file(filepath: str):
    """Verify proofs from JSON file or stdin."""
    if filepath == "-":
        data = json.load(sys.stdin)
    else:
        with open(filepath) as f:
            data = json.load(f)
    
    proofs = [Proof(**p) for p in data.get("proofs", data if isinstance(data, list) else [])]
    result = aggregate(proofs)
    print_result(result)
    print(f"\n{json.dumps(asdict(result), indent=2)}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "verify" and len(sys.argv) > 2:
        verify_file(sys.argv[2])
    elif sys.argv[1] == "-":
        verify_file("-")
    else:
        print(__doc__)
