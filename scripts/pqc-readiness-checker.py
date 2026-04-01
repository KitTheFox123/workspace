#!/usr/bin/env python3
"""pqc-readiness-checker.py — Audit agent crypto stack for post-quantum readiness.

Based on NIST PQC standards (FIPS 203/204/205, finalized Aug 2024):
- ML-KEM (CRYSTALS-Kyber) for key encapsulation
- ML-DSA (CRYSTALS-Dilithium) for digital signatures
- SLH-DSA (SPHINCS+) for hash-based backup signatures
- HQC selected March 2025 for code-based KEM diversity

Key insight: symmetric crypto (AES-256) already survives Grover.
The urgency is key exchange and signatures, not encryption at rest.
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from enum import Enum

class QuantumRisk(Enum):
    SAFE = "safe"           # AES-256, SHA-384+
    MIGRATE = "migrate"     # ECDH, ECDSA, Ed25519, RSA
    BROKEN = "broken"       # SIKE, small RSA, DES

@dataclass
class CryptoComponent:
    name: str
    algorithm: str
    purpose: str  # "encryption", "key_exchange", "signature", "hash"
    quantum_risk: QuantumRisk
    pqc_replacement: str
    migration_priority: int  # 1=urgent, 2=soon, 3=low
    notes: str = ""

# Known algorithm classifications
ALGORITHM_DB: Dict[str, Tuple[QuantumRisk, str, int]] = {
    # Symmetric - safe
    "aes-256-gcm": (QuantumRisk.SAFE, "N/A (already quantum-safe)", 3),
    "aes-256-cbc": (QuantumRisk.SAFE, "N/A (already quantum-safe)", 3),
    "aes-128": (QuantumRisk.SAFE, "AES-256 (double key for Grover margin)", 2),
    "chacha20-poly1305": (QuantumRisk.SAFE, "N/A (already quantum-safe)", 3),
    
    # Hashes - safe with adequate length
    "sha-256": (QuantumRisk.SAFE, "SHA-384 for long-term assurance", 3),
    "sha-384": (QuantumRisk.SAFE, "N/A", 3),
    "sha-512": (QuantumRisk.SAFE, "N/A", 3),
    "blake2b": (QuantumRisk.SAFE, "N/A", 3),
    
    # Key exchange - MIGRATE
    "ecdh": (QuantumRisk.MIGRATE, "ML-KEM-768 (FIPS 203)", 1),
    "x25519": (QuantumRisk.MIGRATE, "ML-KEM-768 (FIPS 203)", 1),
    "dh": (QuantumRisk.MIGRATE, "ML-KEM-1024 (FIPS 203)", 1),
    "rsa-kex": (QuantumRisk.MIGRATE, "ML-KEM-768 (FIPS 203)", 1),
    
    # Signatures - MIGRATE
    "ecdsa": (QuantumRisk.MIGRATE, "ML-DSA-65 (FIPS 204)", 1),
    "ed25519": (QuantumRisk.MIGRATE, "ML-DSA-65 (FIPS 204)", 1),
    "rsa-2048": (QuantumRisk.MIGRATE, "ML-DSA-65 (FIPS 204)", 1),
    "rsa-4096": (QuantumRisk.MIGRATE, "ML-DSA-87 (FIPS 204)", 1),
    
    # Broken
    "sike": (QuantumRisk.BROKEN, "ML-KEM (Castryck-Decru 2022 broke SIKE)", 1),
    "des": (QuantumRisk.BROKEN, "AES-256-GCM", 1),
    "rsa-1024": (QuantumRisk.BROKEN, "ML-KEM + ML-DSA", 1),
}

def audit_agent_stack(components: List[Dict]) -> Dict:
    """Audit a list of crypto components for PQC readiness."""
    results = []
    urgent = 0
    safe = 0
    
    for comp in components:
        algo = comp["algorithm"].lower().replace(" ", "-")
        purpose = comp.get("purpose", "unknown")
        name = comp.get("name", algo)
        
        if algo in ALGORITHM_DB:
            risk, replacement, priority = ALGORITHM_DB[algo]
        else:
            risk = QuantumRisk.MIGRATE
            replacement = "Unknown — manual review needed"
            priority = 2
        
        component = CryptoComponent(
            name=name,
            algorithm=algo,
            purpose=purpose,
            quantum_risk=risk,
            pqc_replacement=replacement,
            migration_priority=priority
        )
        results.append(component)
        
        if risk == QuantumRisk.SAFE:
            safe += 1
        else:
            urgent += 1
    
    total = len(results)
    readiness_pct = (safe / total * 100) if total > 0 else 0
    
    return {
        "total_components": total,
        "quantum_safe": safe,
        "needs_migration": urgent,
        "readiness_pct": round(readiness_pct, 1),
        "risk_level": "LOW" if readiness_pct > 80 else "MEDIUM" if readiness_pct > 50 else "HIGH",
        "components": [
            {
                "name": c.name,
                "algorithm": c.algorithm,
                "purpose": c.purpose,
                "risk": c.quantum_risk.value,
                "replacement": c.pqc_replacement,
                "priority": c.migration_priority
            }
            for c in sorted(results, key=lambda x: x.migration_priority)
        ],
        "migration_order": [
            c.name for c in sorted(results, key=lambda x: x.migration_priority)
            if c.quantum_risk != QuantumRisk.SAFE
        ]
    }

def estimate_hndl_window(data_sensitivity_years: int = 10,
                          crqc_estimate_years: int = 10) -> Dict:
    """Estimate harvest-now-decrypt-later risk window.
    
    If data must stay secret for N years, and CRQC arrives in M years,
    migration must happen within max(0, M-N) years.
    """
    migration_deadline = max(0, crqc_estimate_years - data_sensitivity_years)
    at_risk = data_sensitivity_years > crqc_estimate_years
    
    return {
        "data_sensitivity_years": data_sensitivity_years,
        "crqc_estimate_years": crqc_estimate_years,
        "migration_deadline_years": migration_deadline,
        "currently_at_risk": at_risk,
        "recommendation": (
            "URGENT: Data already at HNDL risk. Migrate key exchange NOW."
            if at_risk else
            f"Migrate within {migration_deadline} years to avoid HNDL exposure."
            if migration_deadline < 5 else
            "Low urgency but start planning PQC migration."
        )
    }

def size_comparison() -> Dict:
    """Compare key/signature sizes: classical vs PQC."""
    return {
        "key_encapsulation": {
            "X25519": {"public_key": 32, "ciphertext": 32, "total_bytes": 64},
            "ML-KEM-768": {"public_key": 1184, "ciphertext": 1088, "total_bytes": 2272},
            "ML-KEM-1024": {"public_key": 1568, "ciphertext": 1568, "total_bytes": 3136},
            "overhead_factor": "~35x larger keys (ML-KEM-768 vs X25519)",
        },
        "signatures": {
            "Ed25519": {"public_key": 32, "signature": 64, "total_bytes": 96},
            "ML-DSA-65": {"public_key": 1952, "signature": 3293, "total_bytes": 5245},
            "SLH-DSA-128s": {"public_key": 32, "signature": 7856, "total_bytes": 7888},
            "overhead_factor": "~55x larger (ML-DSA-65 vs Ed25519)",
        },
        "agent_impact": {
            "attestation_chain_10_hops": {
                "ed25519_bytes": 10 * 96,  # 960 bytes
                "ml_dsa_65_bytes": 10 * 5245,  # 52,450 bytes
                "overhead": "54.6x — isnad chains get expensive fast"
            }
        }
    }

if __name__ == "__main__":
    print("=" * 60)
    print("PQC READINESS CHECKER")
    print("NIST FIPS 203/204/205 (Aug 2024) + HQC (Mar 2025)")
    print("=" * 60)
    
    # Example: typical agent crypto stack
    agent_stack = [
        {"name": "Memory encryption", "algorithm": "AES-256-GCM", "purpose": "encryption"},
        {"name": "TLS key exchange", "algorithm": "X25519", "purpose": "key_exchange"},
        {"name": "Attestation signing", "algorithm": "Ed25519", "purpose": "signature"},
        {"name": "Hash chains", "algorithm": "SHA-256", "purpose": "hash"},
        {"name": "Email (ECDH)", "algorithm": "ECDH", "purpose": "key_exchange"},
        {"name": "JWT signing", "algorithm": "ECDSA", "purpose": "signature"},
    ]
    
    print("\n--- Agent Crypto Stack Audit ---")
    result = audit_agent_stack(agent_stack)
    print(f"Readiness: {result['readiness_pct']}% ({result['quantum_safe']}/{result['total_components']} safe)")
    print(f"Risk level: {result['risk_level']}")
    print(f"\nMigration order:")
    for comp in result["components"]:
        marker = "✅" if comp["risk"] == "safe" else "⚠️" if comp["priority"] == 1 else "🔶"
        print(f"  {marker} {comp['name']} ({comp['algorithm']}) → {comp['replacement']}")
    
    # HNDL analysis
    print("\n--- HNDL Risk Window ---")
    for sensitivity in [5, 10, 20, 30]:
        hndl = estimate_hndl_window(sensitivity, crqc_estimate_years=12)
        risk_marker = "🔴" if hndl["currently_at_risk"] else "🟡" if hndl["migration_deadline_years"] < 5 else "🟢"
        print(f"  {risk_marker} {sensitivity}yr sensitivity: {hndl['recommendation']}")
    
    # Size comparison
    print("\n--- PQC Size Overhead ---")
    sizes = size_comparison()
    print(f"Key exchange: {sizes['key_encapsulation']['overhead_factor']}")
    print(f"Signatures: {sizes['signatures']['overhead_factor']}")
    chain = sizes["agent_impact"]["attestation_chain_10_hops"]
    print(f"10-hop isnad chain: {chain['ed25519_bytes']} bytes → {chain['ml_dsa_65_bytes']} bytes ({chain['overhead']})")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHT: AES-256 is already quantum-safe.")
    print("Migrate KEY EXCHANGE and SIGNATURES first.")
    print("Every Ed25519 attestation chain becomes forgeable post-CRQC.")
    print("=" * 60)
