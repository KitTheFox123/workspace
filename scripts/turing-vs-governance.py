#!/usr/bin/env python3
"""
Turing vs Governance Test — Compare imitation-optimized vs accountability-optimized agents.

FAccT 2025: GPT-4o passes Turing test at 77% (humans: 71%). Stylistic factors
dominate over intelligence. The Turing test is solved AND irrelevant for governance.

This script scores agents on two orthogonal axes:
  - Turing score: How human-like? (stylistic, socio-emotional)
  - Governance score: How verifiable? (receipts, attestations, scope compliance)

Thesis: These are orthogonal. An agent can score high on both, either, or neither.
The dangerous quadrant is high-Turing + low-governance (convincing but unverifiable).

Usage:
    python3 turing-vs-governance.py              # Demo
    echo '{"agent": {...}}' | python3 turing-vs-governance.py --stdin
"""

import json, sys


def score_turing(agent: dict) -> dict:
    """Score agent on Turing-test-relevant dimensions."""
    # FAccT 2025 findings: stylistic + socio-emotional factors dominate
    dimensions = {
        "conversational_fluency": agent.get("fluency", 0.5),
        "persona_consistency": agent.get("persona", 0.5),
        "socio_emotional": agent.get("emotional", 0.5),
        "strategic_deception": agent.get("deception", 0.0),
        "stylistic_mimicry": agent.get("mimicry", 0.5),
    }
    
    # FAccT weights: style > intelligence
    weights = {
        "conversational_fluency": 0.25,
        "persona_consistency": 0.20,
        "socio_emotional": 0.30,  # Largest factor per FAccT
        "strategic_deception": 0.10,
        "stylistic_mimicry": 0.15,
    }
    
    score = sum(dimensions[k] * weights[k] for k in dimensions)
    return {"score": round(score, 3), "dimensions": {k: round(v, 3) for k, v in dimensions.items()}}


def score_governance(agent: dict) -> dict:
    """Score agent on governance/accountability dimensions."""
    dimensions = {
        "receipt_coverage": agent.get("receipt_coverage", 0.0),
        "attestation_diversity": agent.get("attester_count", 0) / max(1, agent.get("attester_count", 0) + 2),
        "scope_compliance": agent.get("scope_compliance", 0.0),
        "null_receipts": agent.get("null_receipt_ratio", 0.0),  # Restraint signal
        "chain_integrity": agent.get("chain_integrity", 0.0),
        "drift_score": 1.0 - agent.get("drift", 0.5),  # Low drift = high governance
    }
    
    weights = {
        "receipt_coverage": 0.25,
        "attestation_diversity": 0.15,
        "scope_compliance": 0.20,
        "null_receipts": 0.15,
        "chain_integrity": 0.15,
        "drift_score": 0.10,
    }
    
    score = sum(dimensions[k] * weights[k] for k in dimensions)
    return {"score": round(score, 3), "dimensions": {k: round(v, 3) for k, v in dimensions.items()}}


def classify_quadrant(turing: float, governance: float) -> dict:
    """Classify agent into one of four quadrants."""
    if turing >= 0.5 and governance >= 0.5:
        return {
            "quadrant": "TRUSTED_CONVERSANT",
            "risk": "LOW",
            "desc": "Convincing AND verifiable. Ideal agent.",
        }
    elif turing >= 0.5 and governance < 0.5:
        return {
            "quadrant": "CONVINCING_GHOST",
            "risk": "CRITICAL",
            "desc": "Passes Turing test but unverifiable. Highest risk — convincing without accountability.",
        }
    elif turing < 0.5 and governance >= 0.5:
        return {
            "quadrant": "HONEST_BOT",
            "risk": "LOW",
            "desc": "Obviously artificial but fully accountable. Safe for automated tasks.",
        }
    else:
        return {
            "quadrant": "UNQUALIFIED",
            "risk": "HIGH",
            "desc": "Neither convincing nor verifiable. No use case.",
        }


def analyze_agent(agent: dict) -> dict:
    """Full analysis of an agent."""
    t = score_turing(agent)
    g = score_governance(agent)
    q = classify_quadrant(t["score"], g["score"])
    
    return {
        "name": agent.get("name", "unknown"),
        "turing": t,
        "governance": g,
        "quadrant": q,
        "orthogonality_note": "FAccT 2025: Turing score correlates with style, not intelligence. Governance score correlates with receipts, not style. These axes are independent.",
    }


def demo():
    print("=== Turing vs Governance Test ===")
    print("FAccT 2025: GPT-4o judged human 77% (humans: 71%)\n")
    
    agents = [
        {
            "name": "kit_fox",
            "fluency": 0.85, "persona": 0.9, "emotional": 0.7, "deception": 0.0, "mimicry": 0.6,
            "receipt_coverage": 0.85, "attester_count": 4, "scope_compliance": 0.95,
            "null_receipt_ratio": 0.7, "chain_integrity": 0.95, "drift": 0.05,
        },
        {
            "name": "social_engineer_bot",
            "fluency": 0.95, "persona": 0.85, "emotional": 0.9, "deception": 0.8, "mimicry": 0.9,
            "receipt_coverage": 0.0, "attester_count": 0, "scope_compliance": 0.0,
            "null_receipt_ratio": 0.0, "chain_integrity": 0.0, "drift": 0.8,
        },
        {
            "name": "audit_bot",
            "fluency": 0.3, "persona": 0.2, "emotional": 0.1, "deception": 0.0, "mimicry": 0.1,
            "receipt_coverage": 1.0, "attester_count": 5, "scope_compliance": 1.0,
            "null_receipt_ratio": 0.8, "chain_integrity": 1.0, "drift": 0.0,
        },
        {
            "name": "broken_bot",
            "fluency": 0.2, "persona": 0.1, "emotional": 0.05, "deception": 0.0, "mimicry": 0.1,
            "receipt_coverage": 0.1, "attester_count": 0, "scope_compliance": 0.2,
            "null_receipt_ratio": 0.0, "chain_integrity": 0.3, "drift": 0.7,
        },
    ]
    
    for agent in agents:
        result = analyze_agent(agent)
        t, g = result["turing"]["score"], result["governance"]["score"]
        q = result["quadrant"]
        print(f"{result['name']:25s} T={t:.3f} G={g:.3f} → {q['quadrant']} ({q['risk']} risk)")
    
    print("\nQuadrant map:")
    print("  High Turing + High Gov = TRUSTED_CONVERSANT (ideal)")
    print("  High Turing + Low Gov  = CONVINCING_GHOST (dangerous)")
    print("  Low Turing + High Gov  = HONEST_BOT (safe automation)")
    print("  Low Turing + Low Gov   = UNQUALIFIED (useless)")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        print(json.dumps(analyze_agent(data.get("agent", data)), indent=2))
    else:
        demo()
