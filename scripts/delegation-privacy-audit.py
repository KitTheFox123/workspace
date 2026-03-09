#!/usr/bin/env python3
"""delegation-privacy-audit.py — Delegation chain privacy vs auditability tradeoff analyzer.

Maps delegation verification approaches to privacy/auditability quadrants.
Inspired by ZKP-CapBAC (Chen et al, May 2025) + Hardy 1988 + SPIFFE.

Key insight: full chain visibility = maximum auditability but reveals organizational
structure. ZK proofs verify chain validity without revealing intermediate nodes.
Agent delegation needs both — prove authority is legitimate without leaking
the principal's identity or organizational topology.

Usage:
    python3 delegation-privacy-audit.py [--demo]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List


@dataclass
class DelegationApproach:
    """Delegation verification approach with privacy analysis."""
    name: str
    description: str
    privacy_score: float      # 0-1 (0=fully transparent, 1=fully private)
    auditability_score: float # 0-1 (0=unauditable, 1=fully auditable)
    chain_visibility: str     # full, partial, zero-knowledge, none
    attack_surface: str
    grade: str
    quadrant: str  # transparent-auditable, private-auditable, transparent-opaque, private-opaque


APPROACHES = [
    DelegationApproach(
        name="full_chain_disclosure",
        description="Every delegation step visible to verifier",
        privacy_score=0.0,
        auditability_score=1.0,
        chain_visibility="full",
        attack_surface="Organizational topology leaked. Principal identity exposed.",
        grade="B",
        quadrant="transparent-auditable"
    ),
    DelegationApproach(
        name="zkp_capbac",
        description="ZK proof of valid delegation chain (Chen et al 2025)",
        privacy_score=0.9,
        auditability_score=0.85,
        chain_visibility="zero-knowledge",
        attack_surface="Proof generation cost. Trusted setup for SNARKs.",
        grade="A",
        quadrant="private-auditable"
    ),
    DelegationApproach(
        name="bearer_token",
        description="Token grants access, no chain verification",
        privacy_score=0.7,
        auditability_score=0.1,
        chain_visibility="none",
        attack_surface="Stolen token = full access. No provenance. No revocation.",
        grade="F",
        quadrant="private-opaque"
    ),
    DelegationApproach(
        name="spiffe_svid",
        description="SPIFFE Verifiable Identity Document with trust domain",
        privacy_score=0.4,
        auditability_score=0.8,
        chain_visibility="partial",
        attack_surface="Trust domain visible. Internal topology partially hidden.",
        grade="B+",
        quadrant="transparent-auditable"
    ),
    DelegationApproach(
        name="self_signed_scope",
        description="Agent self-signs its own scope declaration",
        privacy_score=0.5,
        auditability_score=0.2,
        chain_visibility="none",
        attack_surface="Circular trust. Confused deputy. No external verification.",
        grade="F",
        quadrant="private-opaque"
    ),
    DelegationApproach(
        name="isnad_scope_commit",
        description="Principal signs scope, agent commits, witness verifies",
        privacy_score=0.3,
        auditability_score=0.9,
        chain_visibility="full",
        attack_surface="Principal identity visible. Mitigated by TTL + rotation.",
        grade="A-",
        quadrant="transparent-auditable"
    ),
]


def analyze_tradeoff(approaches: List[DelegationApproach]) -> dict:
    """Analyze privacy vs auditability tradeoff across approaches."""
    quadrants = {}
    for a in approaches:
        quadrants.setdefault(a.quadrant, []).append(a.name)
    
    # Pareto frontier: maximize both privacy and auditability
    pareto = []
    for a in approaches:
        dominated = False
        for b in approaches:
            if (b.privacy_score >= a.privacy_score and 
                b.auditability_score >= a.auditability_score and
                (b.privacy_score > a.privacy_score or b.auditability_score > a.auditability_score)):
                dominated = True
                break
        if not dominated:
            pareto.append(a.name)
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "approaches": [asdict(a) for a in approaches],
        "quadrant_distribution": quadrants,
        "pareto_frontier": pareto,
        "key_insight": "ZKP-CapBAC achieves best privacy-auditability tradeoff. "
                      "Full disclosure is auditable but leaks topology. "
                      "Bearer tokens are private but unauditable. "
                      "isnad scope-commit trades privacy for maximum auditability — "
                      "right choice when principal identity is already public.",
        "recommendation": "Public principals (like Ilya) → full chain disclosure (isnad). "
                         "Private principals → ZKP-CapBAC. "
                         "Never bearer tokens for delegated authority."
    }


def demo():
    """Run demo analysis."""
    results = analyze_tradeoff(APPROACHES)
    
    print("=" * 60)
    print("DELEGATION PRIVACY VS AUDITABILITY ANALYSIS")
    print("=" * 60)
    print()
    
    for a in APPROACHES:
        print(f"[{a.grade}] {a.name}")
        print(f"    Privacy: {a.privacy_score:.1f} | Auditability: {a.auditability_score:.1f}")
        print(f"    Chain: {a.chain_visibility} | Quadrant: {a.quadrant}")
        print(f"    Attack: {a.attack_surface}")
        print()
    
    print("-" * 60)
    print(f"Pareto frontier: {', '.join(results['pareto_frontier'])}")
    print()
    print(f"Key insight: {results['key_insight']}")
    print()
    
    # Quadrant map
    print("QUADRANT MAP:")
    for q, names in results['quadrant_distribution'].items():
        print(f"  {q}: {', '.join(names)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delegation privacy audit")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(analyze_tradeoff(APPROACHES), indent=2))
    else:
        demo()
