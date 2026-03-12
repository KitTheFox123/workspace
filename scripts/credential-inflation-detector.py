#!/usr/bin/env python3
"""
Credential Inflation Detector — Detect pooling equilibrium collapse in agent reputation.

When everyone has the same credentials, credentials carry zero information (pooling).
Rezi 2026: entry-level jobs now demand 2-3yr experience because degrees don't separate.
Same pattern for agents: benchmark scores, stated capabilities, endorsements → inflation.

Receipts resist inflation because:
1. Supply is constrained (requires actual delivery)
2. Each receipt is unique (can't copy someone else's chain)
3. Verification is cheap (hash check, not interview)

Usage:
    python3 credential-inflation-detector.py              # Demo
    echo '{"population": [...]}' | python3 credential-inflation-detector.py --stdin
"""

import json, sys, math
from collections import Counter

def detect_inflation(population: list[dict]) -> dict:
    """Detect credential inflation in a population of agents."""
    if len(population) < 2:
        return {"inflation_detected": False, "reason": "Need 2+ agents to compare"}
    
    # Count credential frequencies
    all_credentials = []
    all_receipts = []
    for agent in population:
        all_credentials.extend(agent.get("credentials", []))
        all_receipts.extend(agent.get("receipt_types", []))
    
    cred_counts = Counter(all_credentials)
    receipt_counts = Counter(all_receipts)
    n_agents = len(population)
    
    # Credential inflation = high frequency credentials (>50% of agents have them)
    inflated_creds = {c: count for c, count in cred_counts.items() 
                      if count / n_agents > 0.5}
    
    # Separating power: how much does each credential type distinguish agents?
    cred_entropy = _entropy(cred_counts, n_agents)
    receipt_entropy = _entropy(receipt_counts, n_agents)
    
    # Pooling detection: if most agents have same credentials
    agents_with_creds = [a for a in population if a.get("credentials")]
    avg_cred_overlap = _avg_overlap(population, "credentials")
    avg_receipt_overlap = _avg_overlap(population, "receipt_types")
    
    # Inflation score (0 = no inflation, 1 = complete pooling)
    if all_credentials:
        inflation_score = len(inflated_creds) / len(set(all_credentials))
    else:
        inflation_score = 0
    
    # Equilibrium classification
    if inflation_score > 0.7 and avg_receipt_overlap < 0.5:
        equilibrium = "CREDENTIAL_POOLING_RECEIPT_SEPARATING"
        diagnosis = "Credentials inflated but receipts still separate. Market shifting to receipt-based hiring."
    elif inflation_score > 0.7:
        equilibrium = "FULL_POOLING"
        diagnosis = "Both credentials and receipts saturated. Need new separating mechanism."
    elif inflation_score < 0.3:
        equilibrium = "SEPARATING"
        diagnosis = "Credentials still carry information. No inflation detected."
    else:
        equilibrium = "MIXED"
        diagnosis = "Partial inflation. Some credentials inflated, others still separate."
    
    return {
        "population_size": n_agents,
        "unique_credentials": len(set(all_credentials)),
        "unique_receipt_types": len(set(all_receipts)),
        "inflated_credentials": inflated_creds,
        "inflation_score": round(inflation_score, 3),
        "credential_entropy": round(cred_entropy, 3),
        "receipt_entropy": round(receipt_entropy, 3),
        "avg_credential_overlap": round(avg_cred_overlap, 3),
        "avg_receipt_overlap": round(avg_receipt_overlap, 3),
        "equilibrium": equilibrium,
        "diagnosis": diagnosis,
    }


def _entropy(counts: Counter, n: int) -> float:
    """Shannon entropy of distribution."""
    if not counts:
        return 0
    total = sum(counts.values())
    probs = [c / total for c in counts.values()]
    return -sum(p * math.log2(p) for p in probs if p > 0)


def _avg_overlap(population: list[dict], field: str) -> float:
    """Average Jaccard overlap between agents for a given field."""
    overlaps = []
    for i, a in enumerate(population):
        for j, b in enumerate(population):
            if i >= j:
                continue
            set_a = set(a.get(field, []))
            set_b = set(b.get(field, []))
            if set_a or set_b:
                jaccard = len(set_a & set_b) / len(set_a | set_b)
                overlaps.append(jaccard)
    return sum(overlaps) / len(overlaps) if overlaps else 0


def demo():
    print("=== Credential Inflation Detector ===")
    print("Spence 1973 + Rezi 2026\n")
    
    # Inflated market: everyone has same creds, different receipts
    inflated = [
        {"name": "agent_1", "credentials": ["benchmark_pass", "certified", "endorsed", "profile_complete"],
         "receipt_types": ["delivery", "x402", "dispute_win"]},
        {"name": "agent_2", "credentials": ["benchmark_pass", "certified", "endorsed", "profile_complete"],
         "receipt_types": ["delivery", "dkim"]},
        {"name": "agent_3", "credentials": ["benchmark_pass", "certified", "endorsed", "profile_complete"],
         "receipt_types": ["x402", "gen_sig", "delivery", "dispute_win"]},
        {"name": "agent_4", "credentials": ["benchmark_pass", "certified", "endorsed", "profile_complete"],
         "receipt_types": ["delivery"]},
        {"name": "agent_5", "credentials": ["benchmark_pass", "certified", "endorsed", "profile_complete"],
         "receipt_types": ["x402", "delivery", "gen_sig", "dkim", "dispute_win"]},
    ]
    
    print("Inflated market (everyone certified + endorsed):")
    r = detect_inflation(inflated)
    print(f"  Inflation: {r['inflation_score']} — {r['equilibrium']}")
    print(f"  Inflated creds: {list(r['inflated_credentials'].keys())}")
    print(f"  Cred overlap: {r['avg_credential_overlap']:.2f} vs Receipt overlap: {r['avg_receipt_overlap']:.2f}")
    print(f"  Diagnosis: {r['diagnosis']}")
    
    # Healthy market: diverse credentials AND receipts
    healthy = [
        {"name": "specialist_1", "credentials": ["security_cert"],
         "receipt_types": ["delivery", "dispute_win"]},
        {"name": "specialist_2", "credentials": ["data_cert"],
         "receipt_types": ["x402", "gen_sig"]},
        {"name": "generalist", "credentials": ["benchmark_90"],
         "receipt_types": ["delivery", "dkim"]},
        {"name": "newcomer", "credentials": [],
         "receipt_types": ["x402"]},
    ]
    
    print("\nHealthy market (diverse credentials):")
    r = detect_inflation(healthy)
    print(f"  Inflation: {r['inflation_score']} — {r['equilibrium']}")
    print(f"  Cred entropy: {r['credential_entropy']:.2f}, Receipt entropy: {r['receipt_entropy']:.2f}")
    print(f"  Diagnosis: {r['diagnosis']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = detect_inflation(data.get("population", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
