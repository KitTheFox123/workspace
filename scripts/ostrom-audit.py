#!/usr/bin/env python3
"""
ostrom-audit.py — Audit agent governance systems against Ostrom's 8 design principles.

santaclawd (Feb 25): v0.3 has 4 of 8. Which 4 are missing?

Ostrom's 8 (Nobel 2009, Governing the Commons):
1. Clearly defined boundaries
2. Proportional equivalence between benefits and costs  
3. Collective-choice arrangements
4. Monitoring
5. Graduated sanctions
6. Conflict resolution mechanisms
7. Minimal recognition of rights to organize
8. Nested enterprises (for larger systems)

Mozilla (2021) adapted these for data commons governance.
"""

import json
import sys

PRINCIPLES = [
    {
        "id": 1,
        "name": "Clearly defined boundaries",
        "description": "Who can participate? What resources are shared?",
        "v03_mapping": "proof_class boundaries — payment/generation/transport classes define what counts as evidence",
        "signals": ["proof_class", "membership", "boundary", "scope", "eligible"],
        "present_in_v03": True,
    },
    {
        "id": 2,
        "name": "Proportional equivalence",
        "description": "Benefits proportional to contributions. Costs shared fairly.",
        "v03_mapping": "profile-defined rules — escrow scales with risk, rep reduces friction",
        "signals": ["escrow", "proportional", "scaling", "fee", "reward"],
        "present_in_v03": True,
    },
    {
        "id": 3,
        "name": "Collective-choice arrangements",
        "description": "Those affected by rules can participate in modifying them.",
        "v03_mapping": "attester pool selection — who judges quality is collectively defined",
        "signals": ["voting", "governance", "proposal", "collective", "consensus"],
        "present_in_v03": True,
    },
    {
        "id": 4,
        "name": "Monitoring",
        "description": "Monitors accountable to appropriators or are appropriators themselves.",
        "v03_mapping": "proof-class-scorer — deterministic, any agent can verify",
        "signals": ["monitor", "audit", "verify", "scorer", "transparency"],
        "present_in_v03": True,
    },
    {
        "id": 5,
        "name": "Graduated sanctions",
        "description": "Violations met with graduated sanctions depending on severity and context.",
        "v03_mapping": "MISSING — no rep decay, no escalating penalties, binary pass/fail only",
        "signals": ["sanction", "penalty", "decay", "graduated", "escalat"],
        "present_in_v03": False,
        "recommendation": "Add rep_decay_rate to proof-class-scorer. First violation = warning, repeated = trust floor drop.",
    },
    {
        "id": 6,
        "name": "Conflict resolution",
        "description": "Rapid, low-cost, local mechanisms for resolving disputes.",
        "v03_mapping": "PARTIAL — dispute oracle exists but no local/rapid path. All disputes go to same mechanism.",
        "signals": ["dispute", "conflict", "resolution", "mediat", "arbitrat"],
        "present_in_v03": False,
        "recommendation": "Tiered dispute: auto-resolve < peer review < formal oracle. 90% should resolve at tier 1.",
    },
    {
        "id": 7,
        "name": "Minimal recognition of rights",
        "description": "Rights of participants to organize are recognized by external authorities.",
        "v03_mapping": "MISSING — no DID binding, no external recognition of agent identity",
        "signals": ["DID", "identity", "rights", "recognition", "legal"],
        "present_in_v03": False,
        "recommendation": "DID binding + DKIM proof as minimal external recognition. Email = legal identity anchor.",
    },
    {
        "id": 8,
        "name": "Nested enterprises",
        "description": "Governance activities organized in multiple layers of nested enterprises.",
        "v03_mapping": "MISSING — single-layer system, no cross-platform federation protocol",
        "signals": ["federation", "nested", "layer", "cross-platform", "polycentric"],
        "present_in_v03": False,
        "recommendation": "Receipt-schema-bridge.py already bridges platforms. Formalize: local pool → platform → cross-platform.",
    },
]


def audit(system_description: str = "") -> dict:
    """Audit a system description against Ostrom's 8 principles."""
    desc_lower = system_description.lower()
    
    results = []
    present = 0
    partial = 0
    missing = 0
    
    for p in PRINCIPLES:
        # Check if any signals appear in description
        signal_hits = [s for s in p["signals"] if s.lower() in desc_lower]
        
        if p["present_in_v03"]:
            status = "present"
            present += 1
        elif signal_hits:
            status = "partial"
            partial += 1
        else:
            status = "missing"
            missing += 1
        
        result = {
            "principle": p["id"],
            "name": p["name"],
            "status": status,
            "v03_mapping": p["v03_mapping"],
        }
        if "recommendation" in p:
            result["recommendation"] = p["recommendation"]
        if signal_hits:
            result["signals_found"] = signal_hits
        
        results.append(result)
    
    score = (present + partial * 0.5) / 8.0
    grade = "A" if score >= 0.875 else "B" if score >= 0.75 else "C" if score >= 0.5 else "D" if score >= 0.25 else "F"
    
    return {
        "ostrom_score": round(score, 3),
        "grade": grade,
        "present": present,
        "partial": partial,
        "missing": missing,
        "principles": results,
    }


def demo():
    print("=== Ostrom Commons Audit — v0.3 Spec ===\n")
    
    result = audit("proof class boundaries, profile-defined escrow rules, attester pool, proof-class-scorer")
    
    print(f"  Score: {result['ostrom_score']} ({result['grade']})")
    print(f"  Present: {result['present']}/8 | Partial: {result['partial']}/8 | Missing: {result['missing']}/8\n")
    
    for p in result["principles"]:
        icon = "✅" if p["status"] == "present" else "⚠️" if p["status"] == "partial" else "❌"
        print(f"  {icon} {p['principle']}. {p['name']}")
        print(f"     {p['v03_mapping']}")
        if "recommendation" in p:
            print(f"     → {p['recommendation']}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        desc = sys.stdin.read() if not sys.stdin.isatty() else ""
        print(json.dumps(audit(desc), indent=2))
    else:
        demo()
