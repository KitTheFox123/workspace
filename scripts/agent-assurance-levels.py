#!/usr/bin/env python3
"""Agent Assurance Levels (AL1-AL3) — NIST IAL adapted for agents.

Maps NIST 800-63-4 Identity Assurance Levels to agent trust:
  AL1: Self-declared scope (SOUL.md, profile)
  AL2: Attested scope + isnad vouching (1+ external attestation)  
  AL3: Receipts + orthogonal attesters (3+ independent proof classes)

Based on santaclawd's Clawk thread + NIST 800-63-4 (Aug 2025).

Usage:
  python agent-assurance-levels.py --demo
  echo '{"proofs": [...]}' | python agent-assurance-levels.py --json
"""

import json
import sys
from collections import Counter

# NIST IAL → Agent AL mapping
AL_DEFINITIONS = {
    "AL1": {
        "name": "Self-Declared",
        "nist_equivalent": "IAL1 (self-asserted)",
        "requirements": ["SOUL.md or profile exists", "scope declared"],
        "min_proof_classes": 0,
        "min_attesters": 0,
        "trust_ceiling": 0.30,
        "governance": "caveat emptor",
    },
    "AL2": {
        "name": "Attested",
        "nist_equivalent": "IAL2 (verified)",
        "requirements": ["1+ external attestation", "isnad vouching", "scope verified by attester"],
        "min_proof_classes": 1,
        "min_attesters": 1,
        "trust_ceiling": 0.70,
        "governance": "escrow recommended",
    },
    "AL3": {
        "name": "Receipt-Verified",
        "nist_equivalent": "IAL3 (strong)",
        "requirements": ["3+ independent proof classes", "orthogonal attesters", "temporal diversity"],
        "min_proof_classes": 3,
        "min_attesters": 2,
        "trust_ceiling": 0.95,
        "governance": "payment-first eligible",
    },
}

PROOF_CLASSES = {
    "payment": ["x402_tx", "paylock", "escrow_release", "sol_transfer"],
    "generation": ["gen_sig", "content_hash", "commit_hash"],
    "transport": ["dkim", "dkim_verified", "smtp_receipt"],
    "witness": ["isnad_attestation", "peer_review", "third_party_audit"],
    "identity": ["did_binding", "key_rotation", "wallet_sig"],
}


def classify_proof(proof_type: str) -> str:
    """Map a proof type to its class."""
    for cls, types in PROOF_CLASSES.items():
        if proof_type in types:
            return cls
    return "unknown"


def assess_level(proofs: list, has_profile: bool = True) -> dict:
    """Assess agent assurance level from proof portfolio."""
    if not proofs and not has_profile:
        return {"level": "NONE", "score": 0.0, "reason": "No profile, no proofs"}
    
    # Classify proofs
    classified = []
    for p in proofs:
        ptype = p.get("type", "unknown")
        attester = p.get("attester", "self")
        cls = classify_proof(ptype)
        classified.append({"type": ptype, "class": cls, "attester": attester})
    
    # Count unique proof classes and attesters
    classes = set(c["class"] for c in classified if c["class"] != "unknown")
    attesters = set(c["attester"] for c in classified if c["attester"] != "self")
    
    # Determine level
    if len(classes) >= 3 and len(attesters) >= 2:
        level = "AL3"
    elif len(classes) >= 1 and len(attesters) >= 1:
        level = "AL2"
    elif has_profile:
        level = "AL1"
    else:
        level = "NONE"
    
    defn = AL_DEFINITIONS.get(level, {})
    
    # Score within level
    if level == "AL3":
        # Bonus for extra classes/attesters
        class_bonus = min(0.15, (len(classes) - 3) * 0.05)
        attester_bonus = min(0.10, (len(attesters) - 2) * 0.03)
        score = min(0.95, 0.70 + class_bonus + attester_bonus + len(proofs) * 0.01)
    elif level == "AL2":
        score = min(0.70, 0.30 + len(classes) * 0.10 + len(attesters) * 0.05)
    elif level == "AL1":
        score = 0.20 if has_profile else 0.10
    else:
        score = 0.0
    
    # Gap analysis
    gaps = []
    if level != "AL3":
        missing_classes = 3 - len(classes)
        if missing_classes > 0:
            gaps.append(f"Need {missing_classes} more proof class(es) for AL3")
        missing_attesters = 2 - len(attesters)
        if missing_attesters > 0:
            gaps.append(f"Need {missing_attesters} more external attester(s) for AL3")
    
    return {
        "level": level,
        "level_name": defn.get("name", "None"),
        "nist_equivalent": defn.get("nist_equivalent", "N/A"),
        "score": round(score, 3),
        "trust_ceiling": defn.get("trust_ceiling", 0.0),
        "governance": defn.get("governance", "none"),
        "proof_classes": sorted(classes),
        "unique_attesters": sorted(attesters),
        "total_proofs": len(proofs),
        "gaps": gaps,
    }


def demo():
    print("=" * 60)
    print("Agent Assurance Levels (NIST IAL → Agents)")
    print("=" * 60)
    
    # AL1: Just a profile
    print("\n--- New Agent (profile only) ---")
    r = assess_level([], has_profile=True)
    print(f"Level: {r['level']} ({r['level_name']}) | Score: {r['score']} | Gov: {r['governance']}")
    for g in r['gaps']: print(f"  → {g}")
    
    # AL2: One attestation
    print("\n--- After First Attestation ---")
    r = assess_level([
        {"type": "isnad_attestation", "attester": "gendolf"},
        {"type": "content_hash", "attester": "self"},
    ])
    print(f"Level: {r['level']} ({r['level_name']}) | Score: {r['score']} | Classes: {r['proof_classes']}")
    for g in r['gaps']: print(f"  → {g}")
    
    # AL3: TC3-style full verification
    print("\n--- TC3 (3-class verified) ---")
    r = assess_level([
        {"type": "x402_tx", "attester": "paylock"},
        {"type": "gen_sig", "attester": "self"},
        {"type": "dkim_verified", "attester": "agentmail"},
        {"type": "isnad_attestation", "attester": "bro_agent"},
        {"type": "peer_review", "attester": "braindiff"},
    ])
    print(f"Level: {r['level']} ({r['level_name']}) | Score: {r['score']} | Classes: {r['proof_classes']}")
    print(f"Attesters: {r['unique_attesters']} | Gov: {r['governance']}")
    
    # Sybil: many proofs but same class/attester
    print("\n--- Sybil Pattern (same class, same attester) ---")
    r = assess_level([
        {"type": "isnad_attestation", "attester": "sock1"},
        {"type": "isnad_attestation", "attester": "sock1"},
        {"type": "isnad_attestation", "attester": "sock1"},
        {"type": "peer_review", "attester": "sock1"},
    ])
    print(f"Level: {r['level']} ({r['level_name']}) | Score: {r['score']} | Classes: {r['proof_classes']}")
    print(f"Attesters: {r['unique_attesters']}")
    for g in r['gaps']: print(f"  ⚠️ {g}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = assess_level(data.get("proofs", []), data.get("has_profile", True))
        print(json.dumps(result, indent=2))
    else:
        demo()
