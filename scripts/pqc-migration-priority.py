#!/usr/bin/env python3
"""pqc-migration-priority.py — Post-quantum migration priority scorer for agent infrastructure.

Key insight: agents have different threat profiles than humans.
- Memory is ephemeral (low HNDL risk)
- Signing keys are long-lived (high forgery risk)
- Attestation chains need decades-long verification
- Session keys rotate frequently (low priority)

Based on: NIST PQC standards (2024), NSA CNSA 2.0 timeline,
Chrome/Signal hybrid deployment experience.
"""

from dataclasses import dataclass
from typing import List
import json

@dataclass
class CryptoAsset:
    name: str
    current_algo: str
    pqc_replacement: str
    lifetime_years: float  # how long does this need to stay secure?
    rotation_frequency_days: float  # how often is it replaced?
    forgery_impact: float  # 0-1, impact if forged/broken
    hndl_risk: float  # 0-1, harvest-now-decrypt-later exposure
    migration_complexity: float  # 0-1, how hard to migrate

def score_migration_priority(asset: CryptoAsset, 
                              crqc_years: float = 7.0) -> dict:
    """Score migration priority for a crypto asset.
    
    crqc_years: estimated years until cryptographically relevant quantum computer.
    Conservative: 10+, moderate: 7, aggressive: 4.
    """
    # Time pressure: does the asset's lifetime extend past CRQC arrival?
    time_pressure = max(0, min(1, (asset.lifetime_years - crqc_years) / crqc_years))
    
    # HNDL urgency: high rotation = low HNDL risk (data is stale before CRQC)
    rotation_protection = min(1, asset.rotation_frequency_days / 365)
    effective_hndl = asset.hndl_risk * (1 - rotation_protection)
    
    # Forgery risk: long-lived signing keys are highest priority
    forgery_urgency = asset.forgery_impact * (asset.lifetime_years / max(crqc_years, 1))
    
    # Combined priority (higher = migrate sooner)
    priority = (
        0.4 * forgery_urgency +
        0.3 * effective_hndl +
        0.2 * time_pressure +
        0.1 * (1 - asset.migration_complexity)  # easier migrations first
    )
    
    return {
        "asset": asset.name,
        "current": asset.current_algo,
        "replacement": asset.pqc_replacement,
        "priority_score": round(priority, 3),
        "time_pressure": round(time_pressure, 3),
        "effective_hndl": round(effective_hndl, 3),
        "forgery_urgency": round(forgery_urgency, 3),
        "recommendation": (
            "MIGRATE NOW" if priority > 0.6 else
            "PLAN MIGRATION" if priority > 0.3 else
            "MONITOR" if priority > 0.1 else
            "LOW PRIORITY"
        )
    }

# Agent-specific crypto assets
AGENT_ASSETS = [
    CryptoAsset(
        name="Identity signing key",
        current_algo="Ed25519",
        pqc_replacement="ML-DSA-65 (Dilithium)",
        lifetime_years=20.0,  # identity persists across model migrations
        rotation_frequency_days=3650,  # rarely rotated
        forgery_impact=0.95,  # can forge attestations, impersonate
        hndl_risk=0.3,  # signatures are public, not encrypted
        migration_complexity=0.6
    ),
    CryptoAsset(
        name="Attestation chain signatures",
        current_algo="Ed25519 (JWS)",
        pqc_replacement="ML-DSA-44 (Dilithium)",
        lifetime_years=15.0,  # trust proofs need long-term verification
        rotation_frequency_days=365,
        forgery_impact=0.9,  # historical trust becomes unreliable
        hndl_risk=0.2,
        migration_complexity=0.5
    ),
    CryptoAsset(
        name="TLS session keys",
        current_algo="X25519 (ECDH)",
        pqc_replacement="ML-KEM-768 + X25519 hybrid",
        lifetime_years=0.01,  # ephemeral, per-session
        rotation_frequency_days=0.01,
        forgery_impact=0.1,
        hndl_risk=0.7,  # but rotation makes it safe
        migration_complexity=0.2  # browsers already doing this
    ),
    CryptoAsset(
        name="Memory encryption (MEMORY.md)",
        current_algo="AES-256-GCM",
        pqc_replacement="AES-256-GCM (already safe)",
        lifetime_years=1.0,  # memory decays, files change daily
        rotation_frequency_days=30,
        forgery_impact=0.3,
        hndl_risk=0.4,
        migration_complexity=0.1  # AES-256 survives Grover's
    ),
    CryptoAsset(
        name="API authentication tokens",
        current_algo="HMAC-SHA256",
        pqc_replacement="HMAC-SHA256 (already safe)",
        lifetime_years=0.1,  # short-lived tokens
        rotation_frequency_days=1,
        forgery_impact=0.5,
        hndl_risk=0.1,
        migration_complexity=0.1
    ),
    CryptoAsset(
        name="Email encryption (S/MIME)",
        current_algo="RSA-2048",
        pqc_replacement="ML-KEM-768",
        lifetime_years=10.0,  # emails archived long-term
        rotation_frequency_days=365,
        forgery_impact=0.4,
        hndl_risk=0.8,  # classic HNDL target
        migration_complexity=0.7
    ),
    CryptoAsset(
        name="Git commit signatures",
        current_algo="Ed25519 (SSH)",
        pqc_replacement="ML-DSA-44",
        lifetime_years=20.0,  # git history is forever
        rotation_frequency_days=365,
        forgery_impact=0.7,  # can forge code provenance
        hndl_risk=0.2,
        migration_complexity=0.4
    ),
]

if __name__ == "__main__":
    print("=" * 65)
    print("POST-QUANTUM MIGRATION PRIORITY — AGENT INFRASTRUCTURE")
    print("Estimated CRQC arrival: 2033 (7 years)")
    print("=" * 65)
    
    results = []
    for asset in AGENT_ASSETS:
        result = score_migration_priority(asset, crqc_years=7.0)
        results.append(result)
    
    # Sort by priority
    results.sort(key=lambda x: -x["priority_score"])
    
    for r in results:
        print(f"\n{'⚠️' if r['recommendation'] == 'MIGRATE NOW' else '📋' if r['recommendation'] == 'PLAN MIGRATION' else '👁️'} {r['asset']}")
        print(f"   {r['current']} → {r['replacement']}")
        print(f"   Priority: {r['priority_score']:.3f} | {r['recommendation']}")
        print(f"   Forgery urgency: {r['forgery_urgency']:.3f} | HNDL risk: {r['effective_hndl']:.3f}")
    
    print("\n" + "=" * 65)
    print("KEY FINDING: Identity signing keys and attestation signatures")
    print("are the #1 migration priority for agents — NOT memory encryption.")
    print("AES-256 already survives Grover's algorithm. Ed25519 does not")
    print("survive Shor's. Signatures > encryption for agent PQC.")
    print("=" * 65)
    
    # Sensitivity analysis
    print("\n--- CRQC Timeline Sensitivity ---")
    for years in [4, 7, 10, 15]:
        top = score_migration_priority(AGENT_ASSETS[0], crqc_years=years)
        mem = score_migration_priority(AGENT_ASSETS[3], crqc_years=years)
        print(f"  CRQC in {years}y: Identity key={top['priority_score']:.3f} ({top['recommendation']}), "
              f"Memory={mem['priority_score']:.3f} ({mem['recommendation']})")
