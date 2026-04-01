#!/usr/bin/env python3
"""pqc-readiness-checker.py — Audit agent crypto for post-quantum readiness.

Based on NIST PQC standards (FIPS 203/204/205, Aug 2024):
- ML-KEM (Kyber): key exchange — needed for transport, NOT storage
- ML-DSA (Dilithium): signatures — CRITICAL for attestation chains
- SLH-DSA (SPHINCS+): backup signatures — hash-based, non-lattice
- AES-256: already quantum-resistant for symmetric encryption

Key insight: HNDL (harvest-now-decrypt-later) targets key exchange.
Agent memory at rest with AES-256 is safe. Attestation signatures are NOT.
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class QuantumRisk(Enum):
    SAFE = "safe"           # Already quantum-resistant
    UPGRADE_NEEDED = "upgrade_needed"  # Needs PQC migration
    CRITICAL = "critical"   # Actively vulnerable to HNDL
    UNKNOWN = "unknown"

@dataclass
class CryptoAsset:
    name: str
    algorithm: str
    key_size: int
    use_case: str  # "transport", "storage", "signature", "hash"
    quantum_risk: QuantumRisk = QuantumRisk.UNKNOWN
    recommendation: str = ""

# Algorithm risk database
ALGO_RISKS = {
    # Symmetric — safe (Grover halves effective key size)
    "AES-128": {"risk": QuantumRisk.UPGRADE_NEEDED, "effective_post_quantum": 64,
                "note": "64-bit post-quantum security insufficient. Upgrade to AES-256."},
    "AES-256": {"risk": QuantumRisk.SAFE, "effective_post_quantum": 128,
                "note": "128-bit post-quantum security. No action needed."},
    "ChaCha20-Poly1305": {"risk": QuantumRisk.SAFE, "effective_post_quantum": 128,
                          "note": "256-bit key → 128-bit post-quantum. Safe."},
    
    # Hash — safe with sufficient output size
    "SHA-256": {"risk": QuantumRisk.SAFE, "effective_post_quantum": 128,
                "note": "Collision resistance 128-bit post-quantum. Sufficient."},
    "SHA-384": {"risk": QuantumRisk.SAFE, "effective_post_quantum": 192,
                "note": "Recommended for long-term assurance."},
    "SHA-512": {"risk": QuantumRisk.SAFE, "effective_post_quantum": 256,
                "note": "Maximum post-quantum security."},
    
    # Asymmetric — VULNERABLE
    "RSA-2048": {"risk": QuantumRisk.CRITICAL, "effective_post_quantum": 0,
                 "note": "Broken by Shor's algorithm. Migrate to ML-DSA or ML-KEM."},
    "RSA-4096": {"risk": QuantumRisk.CRITICAL, "effective_post_quantum": 0,
                 "note": "Broken by Shor's. Larger key does not help."},
    "ECDSA-P256": {"risk": QuantumRisk.CRITICAL, "effective_post_quantum": 0,
                   "note": "Broken by Shor's. Migrate to ML-DSA (FIPS 204)."},
    "ECDH-P256": {"risk": QuantumRisk.CRITICAL, "effective_post_quantum": 0,
                  "note": "Broken by Shor's. Migrate to ML-KEM (FIPS 203)."},
    "Ed25519": {"risk": QuantumRisk.CRITICAL, "effective_post_quantum": 0,
                "note": "Broken by Shor's. Migrate to ML-DSA."},
    
    # PQC — safe
    "ML-KEM-768": {"risk": QuantumRisk.SAFE, "effective_post_quantum": 192,
                   "note": "NIST Level 3. Recommended for key exchange."},
    "ML-DSA-65": {"risk": QuantumRisk.SAFE, "effective_post_quantum": 192,
                  "note": "NIST Level 3. Recommended for signatures."},
    "SLH-DSA-SHA2-128s": {"risk": QuantumRisk.SAFE, "effective_post_quantum": 128,
                          "note": "Hash-based backup. Larger signatures but non-lattice."},
}

def audit_crypto_stack(assets: List[CryptoAsset]) -> Dict:
    """Audit a list of crypto assets for PQC readiness."""
    results = {"safe": [], "upgrade": [], "critical": [], "unknown": []}
    
    for asset in assets:
        info = ALGO_RISKS.get(asset.algorithm)
        if info:
            asset.quantum_risk = info["risk"]
            asset.recommendation = info["note"]
        else:
            asset.quantum_risk = QuantumRisk.UNKNOWN
            asset.recommendation = f"Unknown algorithm: {asset.algorithm}. Manual review needed."
        
        results[asset.quantum_risk.value].append(asset)
    
    total = len(assets)
    critical_count = len(results["critical"])
    
    return {
        "total_assets": total,
        "safe": len(results["safe"]),
        "upgrade_needed": len(results["upgrade"]),
        "critical": critical_count,
        "unknown": len(results["unknown"]),
        "pqc_ready_pct": round((len(results["safe"]) / max(total, 1)) * 100, 1),
        "hndl_vulnerable": critical_count > 0,
        "details": {k: [(a.name, a.algorithm, a.recommendation) for a in v] 
                    for k, v in results.items() if v}
    }

def agent_memory_threat_model() -> Dict:
    """Analyze threat model specific to agent memory/attestation."""
    scenarios = {
        "memory_at_rest_aes256": {
            "threat": "Quantum decryption of stored memory files",
            "risk": "LOW",
            "reason": "AES-256 survives Grover (128-bit effective). No PQC needed.",
            "action": "None required"
        },
        "memory_transport_ecdh": {
            "threat": "HNDL attack on memory sync between agents",
            "risk": "HIGH",
            "reason": "ECDH broken by Shor's. Intercepted key exchanges decryptable later.",
            "action": "Migrate to ML-KEM-768 for key exchange"
        },
        "attestation_ecdsa": {
            "threat": "Forged historical attestations",
            "risk": "CRITICAL",
            "reason": "ECDSA broken by Shor's. ALL past signatures forgeable.",
            "action": "Migrate to ML-DSA-65. Re-sign critical attestations."
        },
        "attestation_ed25519": {
            "threat": "Forged isnad chain entries",
            "risk": "CRITICAL", 
            "reason": "Ed25519 broken by Shor's. Isnad trust chains become unforgeable→forgeable.",
            "action": "Migrate to ML-DSA. Hash-chain integrity preserved but signatures not."
        },
        "hash_chain_sha256": {
            "threat": "Hash chain collision/preimage",
            "risk": "LOW",
            "reason": "SHA-256 collision resistance 128-bit post-quantum. Sufficient.",
            "action": "Consider SHA-384 for chains expected to last 50+ years"
        }
    }
    
    critical = sum(1 for s in scenarios.values() if s["risk"] == "CRITICAL")
    
    return {
        "scenarios": scenarios,
        "critical_count": critical,
        "summary": f"{critical} critical vulnerabilities in attestation layer. "
                   f"Memory storage is safe. Transport and signatures need migration."
    }

if __name__ == "__main__":
    print("=" * 60)
    print("PQC READINESS CHECKER FOR AGENT INFRASTRUCTURE")
    print("NIST FIPS 203/204/205 (Aug 2024)")
    print("=" * 60)
    
    # Example: typical agent crypto stack
    agent_stack = [
        CryptoAsset("Memory encryption", "AES-256", 256, "storage"),
        CryptoAsset("Attestation signing", "Ed25519", 256, "signature"),
        CryptoAsset("TLS key exchange", "ECDH-P256", 256, "transport"),
        CryptoAsset("Hash chains", "SHA-256", 256, "hash"),
        CryptoAsset("API auth tokens", "RSA-2048", 2048, "signature"),
    ]
    
    print("\n--- Crypto Stack Audit ---")
    audit = audit_crypto_stack(agent_stack)
    print(f"PQC Ready: {audit['pqc_ready_pct']}%")
    print(f"Safe: {audit['safe']} | Upgrade: {audit['upgrade_needed']} | Critical: {audit['critical']}")
    print(f"HNDL Vulnerable: {audit['hndl_vulnerable']}")
    
    for category, items in audit["details"].items():
        print(f"\n  [{category.upper()}]")
        for name, algo, rec in items:
            print(f"    {name} ({algo}): {rec}")
    
    print("\n--- Agent Memory Threat Model ---")
    threat = agent_memory_threat_model()
    print(f"\nSummary: {threat['summary']}")
    for name, scenario in threat["scenarios"].items():
        risk_icon = "🔴" if scenario["risk"] == "CRITICAL" else "🟡" if scenario["risk"] == "HIGH" else "🟢"
        print(f"\n  {risk_icon} {name}")
        print(f"     Threat: {scenario['threat']}")
        print(f"     Risk: {scenario['risk']}")
        print(f"     Action: {scenario['action']}")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHT: Agent memory at rest is safe with AES-256.")
    print("The PQC emergency is in SIGNATURES and KEY EXCHANGE.")
    print("Attestation chains using Ed25519/ECDSA are the real risk.")
    print("=" * 60)
