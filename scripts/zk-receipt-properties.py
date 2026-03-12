#!/usr/bin/env python3
"""ZK-Receipt Property Prover — prove aggregate properties of receipt chains
without revealing individual receipts.

Simulates ZK-style proofs for agent reputation claims:
- "1000 receipts, drift < 5%" — verifiable without exposing clients
- "Lindy > 90 days" — prove longevity without timestamps
- "restraint_ratio > 0.3" — prove self-restraint without action logs

Based on:
- Samsung/Wiley 2025: ZKPs for selective disclosure
- santaclawd: ZK-receipt as privacy layer for attestation chains
- NIST supply chain traceability meta-framework (Oct 2024)

Usage:
  python zk-receipt-properties.py --demo
  echo '{"receipts": [...], "claims": [...]}' | python zk-receipt-properties.py --json
"""

import json
import sys
import hashlib
import math
from datetime import datetime, timedelta
import random

def hash_receipt(receipt: dict) -> str:
    """Content-addressable hash of a receipt."""
    canonical = json.dumps(receipt, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def compute_commitment(receipts: list) -> dict:
    """Compute Pedersen-style commitment to receipt chain (simulated)."""
    hashes = [hash_receipt(r) for r in receipts]
    # Merkle root (simplified)
    combined = hashlib.sha256("".join(sorted(hashes)).encode()).hexdigest()
    return {
        "merkle_root": combined[:32],
        "receipt_count": len(receipts),
        "commitment_time": datetime.utcnow().isoformat() + "Z",
    }


def prove_property(receipts: list, claim: dict) -> dict:
    """Generate a ZK-style proof for a claimed property of the receipt chain."""
    claim_type = claim.get("type")
    
    if claim_type == "receipt_count_gte":
        threshold = claim["value"]
        actual = len(receipts)
        valid = actual >= threshold
        return {
            "claim": f"receipt_count >= {threshold}",
            "valid": valid,
            "proof": {
                "type": "range_proof",
                "committed_count": actual,
                "threshold": threshold,
                "satisfied": valid,
            },
            "revealed": ["count"],
            "hidden": ["individual receipts", "clients", "amounts"],
        }
    
    elif claim_type == "drift_below":
        threshold = claim["value"]
        # Drift = std dev of quality scores / mean
        scores = [r.get("score", r.get("quality", 0.5)) for r in receipts]
        if not scores or sum(scores) == 0:
            return {"claim": f"drift < {threshold}", "valid": False, "error": "no scores"}
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        drift = math.sqrt(variance) / mean if mean > 0 else float('inf')
        valid = drift < threshold
        return {
            "claim": f"drift < {threshold}",
            "valid": valid,
            "proof": {
                "type": "statistical_proof",
                "drift": round(drift, 4),
                "threshold": threshold,
                "n": len(scores),
            },
            "revealed": ["drift_coefficient", "n"],
            "hidden": ["individual scores", "client identities", "timestamps"],
        }
    
    elif claim_type == "lindy_above":
        days = claim["value"]
        timestamps = []
        for r in receipts:
            if "timestamp" in r:
                try:
                    ts = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
                    timestamps.append(ts)
                except:
                    pass
        if len(timestamps) < 2:
            return {"claim": f"lindy > {days}d", "valid": False, "error": "insufficient timestamps"}
        
        span = (max(timestamps) - min(timestamps)).total_seconds() / 86400
        valid = span > days
        return {
            "claim": f"lindy > {days} days",
            "valid": valid,
            "proof": {
                "type": "range_proof",
                "span_days": round(span, 1),
                "threshold_days": days,
                "satisfied": valid,
            },
            "revealed": ["span_days"],
            "hidden": ["exact timestamps", "receipt contents", "client identities"],
        }
    
    elif claim_type == "restraint_ratio_above":
        threshold = claim["value"]
        approved = sum(1 for r in receipts if r.get("approved", False))
        taken = sum(1 for r in receipts if r.get("action_taken") is not None)
        if approved == 0:
            return {"claim": f"restraint > {threshold}", "valid": False, "error": "no approved actions"}
        
        # Restraint = approved but NOT taken / total approved
        restrained = approved - taken
        ratio = restrained / approved
        valid = ratio > threshold
        return {
            "claim": f"restraint_ratio > {threshold}",
            "valid": valid,
            "proof": {
                "type": "ratio_proof",
                "restraint_ratio": round(ratio, 4),
                "threshold": threshold,
                "approved_count": approved,
            },
            "revealed": ["restraint_ratio", "approved_count"],
            "hidden": ["specific actions", "client data", "what was restrained"],
        }
    
    elif claim_type == "diversity_above":
        threshold = claim["value"]
        types = set(r.get("proof_type", r.get("type", "unknown")) for r in receipts)
        n_types = len(types)
        max_possible = 7  # payment, generation, transport, witness, isnad, delegation, restraint
        diversity = n_types / max_possible
        valid = diversity > threshold
        return {
            "claim": f"proof_diversity > {threshold}",
            "valid": valid,
            "proof": {
                "type": "set_membership_proof",
                "unique_types": n_types,
                "diversity_score": round(diversity, 3),
            },
            "revealed": ["type_count", "diversity_score"],
            "hidden": ["which types", "receipt contents"],
        }
    
    else:
        return {"claim": claim_type, "valid": False, "error": f"unknown claim type: {claim_type}"}


def verify_bundle(receipts: list, claims: list) -> dict:
    """Verify a bundle of claims against a receipt chain."""
    commitment = compute_commitment(receipts)
    proofs = [prove_property(receipts, c) for c in claims]
    
    all_valid = all(p["valid"] for p in proofs)
    
    # What's revealed vs hidden
    all_revealed = set()
    all_hidden = set()
    for p in proofs:
        all_revealed.update(p.get("revealed", []))
        all_hidden.update(p.get("hidden", []))
    
    return {
        "commitment": commitment,
        "claims_count": len(claims),
        "all_valid": all_valid,
        "proofs": proofs,
        "privacy_summary": {
            "revealed": sorted(all_revealed),
            "hidden": sorted(all_hidden),
        },
        "grade": "VERIFIED" if all_valid else "FAILED",
    }


def generate_demo_receipts(n=100, quality=0.85, days=120):
    """Generate realistic demo receipt chain."""
    receipts = []
    base_time = datetime.utcnow() - timedelta(days=days)
    types = ["payment", "generation", "transport", "witness", "isnad"]
    
    for i in range(n):
        ts = base_time + timedelta(hours=random.uniform(0, days * 24))
        score = max(0, min(1, random.gauss(quality, 0.05)))
        approved = random.random() < 0.7  # 70% had approvals
        taken = approved and random.random() < 0.6  # 60% of approved were taken
        
        receipts.append({
            "id": hashlib.sha256(f"receipt-{i}".encode()).hexdigest()[:12],
            "timestamp": ts.isoformat() + "Z",
            "score": round(score, 3),
            "quality": round(score, 3),
            "proof_type": random.choice(types),
            "approved": approved,
            "action_taken": "completed" if taken else None,
        })
    
    return receipts


def demo():
    print("=" * 60)
    print("ZK-Receipt Property Prover")
    print("=" * 60)
    
    # Scenario 1: Strong agent (100 receipts, 120 days, high quality)
    print("\n--- Scenario 1: Established Agent ---")
    receipts = generate_demo_receipts(n=100, quality=0.88, days=120)
    claims = [
        {"type": "receipt_count_gte", "value": 50},
        {"type": "drift_below", "value": 0.10},
        {"type": "lindy_above", "value": 90},
        {"type": "restraint_ratio_above", "value": 0.20},
        {"type": "diversity_above", "value": 0.50},
    ]
    result = verify_bundle(receipts, claims)
    print(f"Grade: {result['grade']}")
    print(f"Commitment: {result['commitment']['merkle_root'][:16]}...")
    for p in result["proofs"]:
        status = "✅" if p["valid"] else "❌"
        print(f"  {status} {p['claim']}")
    print(f"Revealed: {', '.join(result['privacy_summary']['revealed'])}")
    print(f"Hidden: {', '.join(result['privacy_summary']['hidden'][:4])}...")
    
    # Scenario 2: New agent trying to claim established
    print("\n--- Scenario 2: New Agent (False Claims) ---")
    new_receipts = generate_demo_receipts(n=8, quality=0.70, days=5)
    result = verify_bundle(new_receipts, claims)
    print(f"Grade: {result['grade']}")
    for p in result["proofs"]:
        status = "✅" if p["valid"] else "❌"
        detail = ""
        if "proof" in p and "drift" in p["proof"]:
            detail = f" (drift={p['proof']['drift']})"
        elif "proof" in p and "span_days" in p["proof"]:
            detail = f" (span={p['proof']['span_days']}d)"
        print(f"  {status} {p['claim']}{detail}")
    
    # Scenario 3: Drifting agent
    print("\n--- Scenario 3: Drifting Agent (High Variance) ---")
    drift_receipts = generate_demo_receipts(n=60, quality=0.50, days=100)
    # Add some wild variance
    for r in drift_receipts[:20]:
        r["score"] = round(random.uniform(0.1, 0.95), 3)
        r["quality"] = r["score"]
    
    drift_claims = [
        {"type": "receipt_count_gte", "value": 50},
        {"type": "drift_below", "value": 0.05},
        {"type": "restraint_ratio_above", "value": 0.25},
    ]
    result = verify_bundle(drift_receipts, drift_claims)
    print(f"Grade: {result['grade']}")
    for p in result["proofs"]:
        status = "✅" if p["valid"] else "❌"
        print(f"  {status} {p['claim']}")


if __name__ == "__main__":
    random.seed(42)
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = verify_bundle(data.get("receipts", []), data.get("claims", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
