#!/usr/bin/env python3
"""pq-attestation-cost.py — Post-quantum attestation chain cost analysis.

Compares classical (Ed25519) vs post-quantum (ML-DSA-65) signature costs
for isnad-style attestation chains at varying depths.

Based on NIST FIPS 203/204 (2024), Duits (2019) runtime overhead estimates.
"""

import json

# Signature sizes in bytes
SCHEMES = {
    "Ed25519": {"sig_bytes": 64, "pk_bytes": 32, "sk_bytes": 64, "verify_us": 70},
    "ML-DSA-44": {"sig_bytes": 2420, "pk_bytes": 1312, "sk_bytes": 2560, "verify_us": 120},
    "ML-DSA-65": {"sig_bytes": 3309, "pk_bytes": 1952, "sk_bytes": 4032, "verify_us": 180},
    "ML-DSA-87": {"sig_bytes": 4627, "pk_bytes": 2592, "sk_bytes": 4896, "verify_us": 260},
}

# KEM sizes for key exchange
KEMS = {
    "Curve25519": {"pk_bytes": 32, "ct_bytes": 32, "ss_bytes": 32, "runtime_factor": 1.0},
    "ML-KEM-512": {"pk_bytes": 800, "ct_bytes": 768, "ss_bytes": 32, "runtime_factor": 1.8},
    "ML-KEM-768": {"pk_bytes": 1184, "ct_bytes": 1088, "ss_bytes": 32, "runtime_factor": 2.3},
    "ML-KEM-1024": {"pk_bytes": 1568, "ct_bytes": 1568, "ss_bytes": 32, "runtime_factor": 3.1},
}

def chain_cost(scheme: str, depth: int) -> dict:
    """Calculate total signature payload for an attestation chain."""
    s = SCHEMES[scheme]
    total_sig = s["sig_bytes"] * depth
    total_pk = s["pk_bytes"] * depth  # each hop includes signer's public key
    total_payload = total_sig + total_pk
    verify_time = s["verify_us"] * depth
    
    return {
        "scheme": scheme,
        "depth": depth,
        "sig_payload_bytes": total_sig,
        "pk_payload_bytes": total_pk,
        "total_bytes": total_payload,
        "total_kb": round(total_payload / 1024, 1),
        "verify_time_us": verify_time,
        "verify_time_ms": round(verify_time / 1000, 2),
    }

def compare_chains(depths: list = None):
    """Compare Ed25519 vs ML-DSA at various chain depths."""
    if depths is None:
        depths = [1, 3, 5, 10, 20, 50]
    
    print("=" * 70)
    print("POST-QUANTUM ATTESTATION CHAIN COST ANALYSIS")
    print("=" * 70)
    
    for depth in depths:
        print(f"\n--- Chain depth: {depth} hops ---")
        for scheme in ["Ed25519", "ML-DSA-65", "ML-DSA-87"]:
            c = chain_cost(scheme, depth)
            bloat = c["total_bytes"] / chain_cost("Ed25519", depth)["total_bytes"]
            print(f"  {scheme:12s}: {c['total_kb']:8.1f} KB | verify: {c['verify_time_ms']:6.2f} ms | bloat: {bloat:.1f}x")

def propagation_analysis():
    """Model how chain weight affects propagation in gossip networks."""
    print("\n" + "=" * 70)
    print("PROPAGATION IMPACT ANALYSIS")
    print("=" * 70)
    
    # Assume gossip network with bandwidth budget per message
    bandwidth_budgets = [1024, 4096, 16384, 65536]  # bytes
    
    for budget in bandwidth_budgets:
        print(f"\n--- Bandwidth budget: {budget} bytes ---")
        for scheme in ["Ed25519", "ML-DSA-65"]:
            s = SCHEMES[scheme]
            per_hop = s["sig_bytes"] + s["pk_bytes"]
            max_depth = budget // per_hop
            print(f"  {scheme:12s}: {per_hop:5d} bytes/hop → max chain depth: {max_depth}")
    
    # Critical finding
    print("\n⚠️  At 4KB budget (typical gossip message):")
    ed_max = 4096 // (64 + 32)
    ml_max = 4096 // (3309 + 1952)
    print(f"  Ed25519:  {ed_max} hops (plenty)")
    print(f"  ML-DSA-65: {ml_max} hops (truncated!)")
    print(f"  PQ chains hit bandwidth ceiling at depth {ml_max}.")
    print(f"  Solutions: signature aggregation, checkpoint compression, or larger budgets.")

def hndl_risk_timeline():
    """Estimate harvest-now-decrypt-later risk for agent attestations."""
    print("\n" + "=" * 70)
    print("HNDL RISK TIMELINE FOR AGENT ATTESTATIONS")
    print("=" * 70)
    
    # Quantum timeline estimates
    scenarios = [
        ("Optimistic (IBM roadmap)", 2029, "1000+ logical qubits"),
        ("Consensus (NIST)", 2035, "Cryptographically relevant"),
        ("Conservative", 2040, "Reliable fault-tolerant"),
    ]
    
    for label, year, desc in scenarios:
        years_from_now = year - 2026
        print(f"\n  {label}: ~{year} ({desc})")
        print(f"    Years of HNDL exposure: {years_from_now}")
        print(f"    Agent attestations created now with Ed25519:")
        print(f"      - Forged retroactively: YES (if keys harvested)")
        print(f"      - Impact: historical trust chains invalidated")
        print(f"    With ML-DSA-65:")
        print(f"      - Forged retroactively: NO (lattice-hard)")
        print(f"      - Cost: 50x signature overhead NOW")
    
    print(f"\n  Trade-off: pay 50x overhead now, or risk total chain")
    print(f"  invalidation in {scenarios[0][1]-2026}-{scenarios[2][1]-2026} years.")
    print(f"  For short-lived attestations (<1yr): Ed25519 fine.")
    print(f"  For reputation chains (multi-year): migrate NOW.")

if __name__ == "__main__":
    compare_chains()
    propagation_analysis()
    hndl_risk_timeline()
    
    print("\n" + "=" * 70)
    print("KEY FINDINGS:")
    print("1. ML-DSA-65 costs 55x per hop vs Ed25519")
    print("2. At 4KB gossip budget: Ed25519 gets 42 hops, ML-DSA gets 0")
    print("3. PQ migration essential for multi-year reputation chains")
    print("4. Short-lived attestations can defer — HNDL risk is time-bounded")
    print("5. Signature aggregation needed to make PQ chains propagate")
    print("=" * 70)
