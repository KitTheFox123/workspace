#!/usr/bin/env python3
"""pqc-migration-cost.py — Post-quantum signature migration cost model for agent attestation chains.

Compares Ed25519 vs ML-DSA (FIPS 204) signature sizes and bandwidth costs
for isnad-style attestation chains at various depths.

Based on:
- NIST FIPS 204 (ML-DSA, Aug 2024)
- Dinu (2025) "Migration to PQC: From ECDSA to ML-DSA"
- DigiCert ML-DSA benchmarks
"""

from dataclasses import dataclass
from typing import List, Dict

@dataclass
class SignatureScheme:
    name: str
    pub_key_bytes: int
    sig_bytes: int
    sign_us: float  # microseconds
    verify_us: float
    security_level: int  # NIST level

SCHEMES = {
    "ed25519": SignatureScheme("Ed25519", 32, 64, 50, 75, 1),
    "ml-dsa-44": SignatureScheme("ML-DSA-44", 1312, 2420, 200, 120, 2),
    "ml-dsa-65": SignatureScheme("ML-DSA-65", 1952, 3309, 400, 230, 3),
    "ml-dsa-87": SignatureScheme("ML-DSA-87", 2592, 4627, 600, 350, 5),
    "hybrid-44": SignatureScheme("Ed25519+ML-DSA-44", 1344, 2484, 250, 195, 2),
    "hybrid-65": SignatureScheme("Ed25519+ML-DSA-65", 1984, 3373, 450, 305, 3),
}

def chain_cost(scheme: SignatureScheme, hops: int) -> Dict:
    """Calculate total chain cost for N-hop attestation chain."""
    total_sig_bytes = scheme.sig_bytes * hops
    total_key_bytes = scheme.pub_key_bytes * hops
    total_bytes = total_sig_bytes + total_key_bytes
    verify_time_us = scheme.verify_us * hops
    
    return {
        "scheme": scheme.name,
        "hops": hops,
        "total_sig_bytes": total_sig_bytes,
        "total_key_bytes": total_key_bytes,
        "total_bytes": total_bytes,
        "total_kb": round(total_bytes / 1024, 1),
        "verify_time_ms": round(verify_time_us / 1000, 2),
    }

def migration_comparison(max_hops: int = 20) -> None:
    """Compare schemes across chain depths."""
    print(f"{'Hops':<6}", end="")
    for name in ["ed25519", "ml-dsa-44", "ml-dsa-65", "hybrid-65"]:
        print(f"{SCHEMES[name].name:<22}", end="")
    print()
    print("-" * 94)
    
    for hops in [1, 3, 5, 10, 15, 20]:
        print(f"{hops:<6}", end="")
        for name in ["ed25519", "ml-dsa-44", "ml-dsa-65", "hybrid-65"]:
            cost = chain_cost(SCHEMES[name], hops)
            print(f"{cost['total_kb']:>6.1f} KB ({cost['verify_time_ms']:>5.2f}ms)  ", end="")
        print()

def bloat_factor() -> None:
    """Show bloat factors relative to Ed25519."""
    ed = SCHEMES["ed25519"]
    print("\nBloat factors (vs Ed25519):")
    print(f"{'Scheme':<22} {'Sig bloat':>10} {'Key bloat':>10} {'Chain bloat':>12}")
    print("-" * 56)
    for name, s in SCHEMES.items():
        if name == "ed25519":
            continue
        sig_bloat = s.sig_bytes / ed.sig_bytes
        key_bloat = s.pub_key_bytes / ed.pub_key_bytes
        chain_bloat = (s.sig_bytes + s.pub_key_bytes) / (ed.sig_bytes + ed.pub_key_bytes)
        print(f"{s.name:<22} {sig_bloat:>9.1f}x {key_bloat:>9.1f}x {chain_bloat:>11.1f}x")

def harvest_now_risk(chain_lifetime_years: int = 10) -> Dict:
    """Model harvest-now-decrypt-later risk for attestation chains.
    
    NIST timeline: deprecate classical by 2030, disallow by 2035.
    Shor's algorithm threat: ~2030-2040 estimated for RSA-2048/ECDSA-256.
    """
    # Estimated years until cryptographically relevant quantum computer
    quantum_estimates = {
        "optimistic": 5,   # 2031
        "moderate": 10,    # 2036
        "conservative": 15 # 2041
    }
    
    results = {}
    for scenario, years_to_quantum in quantum_estimates.items():
        vulnerable = chain_lifetime_years > years_to_quantum
        risk = "CRITICAL" if vulnerable else "LOW"
        years_exposed = max(0, chain_lifetime_years - years_to_quantum)
        results[scenario] = {
            "quantum_arrival": 2026 + years_to_quantum,
            "chain_expires": 2026 + chain_lifetime_years,
            "vulnerable": vulnerable,
            "years_exposed": years_exposed,
            "risk": risk,
            "recommendation": "migrate NOW" if vulnerable else "plan migration"
        }
    
    return results

if __name__ == "__main__":
    print("=" * 60)
    print("PQC MIGRATION COST MODEL FOR AGENT ATTESTATION")
    print("NIST FIPS 204 (ML-DSA) vs Ed25519")
    print("=" * 60)
    
    print("\n--- Chain Cost by Depth (sig + pubkey bytes) ---")
    migration_comparison()
    
    bloat_factor()
    
    print("\n--- Harvest-Now-Decrypt-Later Risk ---")
    print("(For attestation chains with 10-year validity)")
    risks = harvest_now_risk(10)
    for scenario, data in risks.items():
        print(f"\n{scenario.upper()} scenario (quantum by {data['quantum_arrival']}):")
        print(f"  Vulnerable: {data['vulnerable']}")
        print(f"  Years exposed: {data['years_exposed']}")
        print(f"  Risk: {data['risk']}")
        print(f"  Action: {data['recommendation']}")
    
    print("\n--- Key Findings ---")
    ed_10 = chain_cost(SCHEMES["ed25519"], 10)
    ml65_10 = chain_cost(SCHEMES["ml-dsa-65"], 10)
    hybrid_10 = chain_cost(SCHEMES["hybrid-65"], 10)
    print(f"10-hop chain: Ed25519={ed_10['total_kb']}KB, ML-DSA-65={ml65_10['total_kb']}KB, Hybrid={hybrid_10['total_kb']}KB")
    print(f"Migration strategy: hybrid signatures during transition (2026-2030)")
    print(f"  - Backward compatible (classical verifiers still work)")
    print(f"  - Forward secure (quantum verifiers validate PQC layer)")
    print(f"  - Cost: {hybrid_10['total_kb']/ed_10['total_kb']:.0f}x bandwidth vs pure classical")
    print(f"Agent attestation: signatures are LONG-LIVED artifacts.")
    print(f"  Harvest-now risk is REAL for chains valid >5 years.")
    print(f"  Migrate signatures FIRST. Encryption can wait.")
