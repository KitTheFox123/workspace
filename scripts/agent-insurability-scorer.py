#!/usr/bin/env python3
"""Agent Insurability Scorer — score agent operations for insurance readiness.

Based on Verisk Jan 2026 AI exclusions (CG 40 47/48, CG 35 08) and the
"silent AI" gap identified by ABA/Lior 2025. Receipt chains as loss dataset.

Cyber insurance grew $0.5B (2012) → $16B (2025) once actuaries got breach data.
Agent insurance needs receipt data FIRST. This tool scores readiness.

Usage:
  python agent-insurability-scorer.py --demo
  echo '{"agent": {...}}' | python agent-insurability-scorer.py --json
"""

import json
import sys
import math

# Verisk addressable dimensions (from CG 40 47/48 analysis)
VERISK_DIMENSIONS = {
    "content_liability": {
        "desc": "Bodily injury/property damage from AI-generated content",
        "weight": 0.20,
        "mitigations": ["content_hash", "generation_sig", "human_review"],
    },
    "advertising_injury": {
        "desc": "Personal/advertising injury from AI content (defamation, IP)",
        "weight": 0.15,
        "mitigations": ["attribution_chain", "license_check", "content_filter"],
    },
    "delegation_liability": {
        "desc": "Principal-agent liability for delegated actions",
        "weight": 0.25,
        "mitigations": ["delegation_proof", "scope_binding", "audit_trail"],
    },
    "data_exposure": {
        "desc": "PII/confidential data handling in agent operations",
        "weight": 0.15,
        "mitigations": ["channel_separation", "data_classification", "encryption"],
    },
    "operational_continuity": {
        "desc": "Service reliability and failure mode documentation",
        "weight": 0.15,
        "mitigations": ["heartbeat_monitoring", "failover_plan", "sla_definition"],
    },
    "attestation_depth": {
        "desc": "Proof chain depth and diversity for auditability",
        "weight": 0.10,
        "mitigations": ["multi_class_proofs", "independent_attesters", "temporal_diversity"],
    },
}


def score_agent(agent: dict) -> dict:
    """Score an agent's insurability across Verisk dimensions."""
    mitigations = set(agent.get("mitigations", []))
    receipt_count = agent.get("receipt_count", 0)
    attestation_classes = agent.get("attestation_classes", 0)
    months_active = agent.get("months_active", 0)
    dispute_rate = agent.get("dispute_rate", 0.5)
    
    dimension_scores = {}
    weighted_total = 0
    
    for dim_id, dim in VERISK_DIMENSIONS.items():
        # Score = proportion of mitigations present
        present = [m for m in dim["mitigations"] if m in mitigations]
        mitigation_score = len(present) / len(dim["mitigations"])
        
        # History bonus (more receipts = more actuarial data)
        history_bonus = min(0.2, math.log1p(receipt_count) / 25)
        
        # Diversity bonus (more attestation classes = less correlated risk)
        diversity_bonus = min(0.15, attestation_classes * 0.05)
        
        # Track record (low dispute rate + time)
        track_bonus = min(0.15, (1 - dispute_rate) * months_active * 0.02)
        
        raw_score = min(1.0, mitigation_score * 0.5 + history_bonus + diversity_bonus + track_bonus)
        
        dimension_scores[dim_id] = {
            "score": round(raw_score, 3),
            "mitigation_coverage": f"{len(present)}/{len(dim['mitigations'])}",
            "mitigations_present": present,
            "mitigations_missing": [m for m in dim["mitigations"] if m not in mitigations],
            "weight": dim["weight"],
        }
        
        weighted_total += raw_score * dim["weight"]
    
    # Overall insurability
    composite = round(weighted_total, 3)
    
    # Premium multiplier (lower = better, 1.0 = standard)
    if composite > 0.8:
        premium_mult = 0.7
        tier = "preferred"
    elif composite > 0.6:
        premium_mult = 1.0
        tier = "standard"
    elif composite > 0.4:
        premium_mult = 1.5
        tier = "substandard"
    elif composite > 0.2:
        premium_mult = 2.5
        tier = "high_risk"
    else:
        premium_mult = None
        tier = "uninsurable"
    
    # Verisk exclusion exposure
    exclusion_risk = []
    if dimension_scores["content_liability"]["score"] < 0.3:
        exclusion_risk.append("CG 40 47 — full gen AI exclusion likely")
    if dimension_scores["advertising_injury"]["score"] < 0.3:
        exclusion_risk.append("CG 40 48 — advertising injury exclusion likely")
    if dimension_scores["delegation_liability"]["score"] < 0.3:
        exclusion_risk.append("CG 35 08 — products/operations exclusion likely")
    
    return {
        "composite_score": composite,
        "tier": tier,
        "premium_multiplier": premium_mult,
        "grade": "A" if composite > 0.8 else "B" if composite > 0.6 else "C" if composite > 0.4 else "D" if composite > 0.2 else "F",
        "dimensions": dimension_scores,
        "exclusion_risk": exclusion_risk if exclusion_risk else ["No immediate exclusion risk"],
        "recommendations": generate_recs(dimension_scores, composite),
    }


def generate_recs(dims, composite):
    recs = []
    # Find weakest dimension
    weakest = min(dims.items(), key=lambda x: x[1]["score"])
    recs.append(f"Priority: improve {weakest[0]} (score: {weakest[1]['score']})")
    
    for dim_id, dim in dims.items():
        if dim["mitigations_missing"]:
            recs.append(f"{dim_id}: add {', '.join(dim['mitigations_missing'])}")
    
    if composite < 0.4:
        recs.append("CRITICAL: Below insurability threshold. Add attestation infrastructure.")
    return recs


def demo():
    print("=" * 60)
    print("Agent Insurability Scorer (Verisk 2026 Framework)")
    print("=" * 60)
    
    # Kit Fox (well-attested)
    kit = {
        "name": "kit_fox",
        "mitigations": [
            "content_hash", "generation_sig", "attribution_chain",
            "delegation_proof", "scope_binding", "audit_trail",
            "channel_separation", "heartbeat_monitoring",
            "multi_class_proofs", "independent_attesters", "temporal_diversity",
        ],
        "receipt_count": 50,
        "attestation_classes": 3,
        "months_active": 1,
        "dispute_rate": 0.0,
    }
    
    print(f"\n--- {kit['name']} (attested agent) ---")
    r = score_agent(kit)
    print(f"Grade: {r['grade']} ({r['composite_score']})")
    print(f"Tier: {r['tier']} | Premium: {r['premium_multiplier']}x")
    print(f"Exclusion risk: {r['exclusion_risk'][0]}")
    
    # Generic bot (no attestation)
    generic = {
        "name": "generic_bot",
        "mitigations": [],
        "receipt_count": 0,
        "attestation_classes": 0,
        "months_active": 6,
        "dispute_rate": 0.15,
    }
    
    print(f"\n--- {generic['name']} (no attestation) ---")
    r = score_agent(generic)
    print(f"Grade: {r['grade']} ({r['composite_score']})")
    print(f"Tier: {r['tier']} | Premium: {r['premium_multiplier']}")
    print(f"Exclusion risk:")
    for er in r['exclusion_risk']:
        print(f"  🚨 {er}")
    
    # Partial (some mitigations)
    partial = {
        "name": "partial_agent",
        "mitigations": [
            "content_hash", "audit_trail", "heartbeat_monitoring",
            "encryption", "sla_definition",
        ],
        "receipt_count": 20,
        "attestation_classes": 1,
        "months_active": 3,
        "dispute_rate": 0.05,
    }
    
    print(f"\n--- {partial['name']} (partial mitigations) ---")
    r = score_agent(partial)
    print(f"Grade: {r['grade']} ({r['composite_score']})")
    print(f"Tier: {r['tier']} | Premium: {r['premium_multiplier']}x")
    print(f"Priority: {r['recommendations'][0]}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        print(json.dumps(score_agent(data.get("agent", data)), indent=2))
    else:
        demo()
