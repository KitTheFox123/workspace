#!/usr/bin/env python3
"""trust-root-selector.py — Interactive trust root axiom selector.

Given deployment constraints (latency tolerance, threat model, 
infrastructure diversity), recommends optimal trust root configuration.

Extends axiom-blast-radius.py with decision logic.

Usage:
    python3 trust-root-selector.py --interactive
    python3 trust-root-selector.py --constraints '{"ttl_hours": 4, "attestors": 3, "infra_providers": 2}'
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass 
class Constraint:
    ttl_hours: float = 24.0
    attestor_count: int = 1
    infra_provider_count: int = 1
    human_available: bool = True
    on_chain: bool = False
    latency_tolerance_ms: int = 5000


@dataclass
class Recommendation:
    primary_axiom: str
    secondary_axiom: str
    tcg_model: str
    estimated_blast_hours: float
    grade: str
    rationale: str
    tools_needed: List[str]


def select_root(c: Constraint) -> Recommendation:
    """Select optimal trust root given constraints."""
    
    # Decision tree based on TCG SRTM/DRTM analysis
    if not c.human_available:
        # No human = must use platform or self-attestation
        if c.attestor_count >= 3 and c.infra_provider_count >= 2:
            return Recommendation(
                primary_axiom="issuer_diversity",
                secondary_axiom="platform_enforcement",
                tcg_model="DRTM",
                estimated_blast_hours=c.ttl_hours,
                grade="B",
                rationale="No human principal available. Diversity of independent attestors "
                         "provides Byzantine tolerance. Requires f < n/3 honest attestors.",
                tools_needed=["confounding-graph-mapper.py", "three-signal-verdict.py",
                            "attestor-selection-sim.py"]
            )
        else:
            return Recommendation(
                primary_axiom="platform_enforcement",
                secondary_axiom="self_attestation",
                tcg_model="SRTM",
                estimated_blast_hours=c.ttl_hours * 10,  # Unbounded without diversity
                grade="D",
                rationale="Insufficient attestor diversity and no human principal. "
                         "Platform enforcement is SRTM — compromise = unbounded damage. "
                         "Add attestors or human oversight.",
                tools_needed=["scope-cert-issuer.py", "liveness-renewal.py"]
            )
    
    # Human available
    if c.ttl_hours <= 4:
        # Short TTL = aggressive DRTM
        return Recommendation(
            primary_axiom="drtm_heartbeat",
            secondary_axiom="human_signs_cert",
            tcg_model="DRTM",
            estimated_blast_hours=c.ttl_hours,
            grade="A",
            rationale=f"Short TTL ({c.ttl_hours}h) bounds blast radius tightly. "
                     "Human signs scope cert at deploy, agent re-attests each heartbeat. "
                     "Key theft exposure = max {c.ttl_hours}h.",
            tools_needed=["scope-cert-issuer.py", "three-signal-verdict.py",
                        "scope-drift-detector.py", "trust-freshness-decay.py"]
        )
    elif c.ttl_hours <= 24:
        return Recommendation(
            primary_axiom="human_signs_cert",
            secondary_axiom="drtm_heartbeat",
            tcg_model="DRTM",
            estimated_blast_hours=c.ttl_hours,
            grade="B+",
            rationale=f"Medium TTL ({c.ttl_hours}h). Human cert + heartbeat re-attestation. "
                     "Consider shortening TTL if threat model allows.",
            tools_needed=["scope-cert-issuer.py", "signal-freshness-decay.py",
                        "scope-drift-detector.py"]
        )
    else:
        # Long TTL
        if c.on_chain:
            return Recommendation(
                primary_axiom="on_chain_provenance",
                secondary_axiom="human_signs_cert",
                tcg_model="SRTM",
                estimated_blast_hours=c.ttl_hours * 5,
                grade="C",
                rationale=f"Long TTL ({c.ttl_hours}h) + on-chain = SRTM model. "
                         "Immutability means compromise damage is permanent. "
                         "Strongly recommend reducing TTL.",
                tools_needed=["axiom-blast-radius.py", "scope-transparency-log.py"]
            )
        else:
            return Recommendation(
                primary_axiom="human_signs_cert",
                secondary_axiom="issuer_diversity",
                tcg_model="DRTM",
                estimated_blast_hours=c.ttl_hours,
                grade="B",
                rationale=f"Long TTL ({c.ttl_hours}h) without on-chain. "
                         "Add issuer diversity for defense in depth. "
                         "Consider heartbeat re-attestation to bound blast radius.",
                tools_needed=["scope-cert-issuer.py", "confounding-graph-mapper.py"]
            )


def demo():
    """Run demo with several constraint profiles."""
    profiles = [
        ("Aggressive (4h TTL, 3 attestors, human)", 
         Constraint(ttl_hours=4, attestor_count=3, infra_provider_count=2, human_available=True)),
        ("Moderate (24h TTL, 1 attestor, human)",
         Constraint(ttl_hours=24, attestor_count=1, infra_provider_count=1, human_available=True)),
        ("Autonomous (no human, 5 attestors)",
         Constraint(ttl_hours=8, attestor_count=5, infra_provider_count=3, human_available=False)),
        ("On-chain (168h TTL, human)",
         Constraint(ttl_hours=168, attestor_count=1, infra_provider_count=1, human_available=True, on_chain=True)),
        ("Minimal (no human, 1 attestor)",
         Constraint(ttl_hours=24, attestor_count=1, infra_provider_count=1, human_available=False)),
    ]
    
    print("=" * 60)
    print("TRUST ROOT SELECTOR — DEPLOYMENT PROFILES")
    print("=" * 60)
    
    for name, constraints in profiles:
        rec = select_root(constraints)
        print(f"\n{'─' * 60}")
        print(f"Profile: {name}")
        print(f"  [{rec.grade}] {rec.primary_axiom} + {rec.secondary_axiom} ({rec.tcg_model})")
        print(f"  Blast radius: ≤{rec.estimated_blast_hours}h")
        print(f"  Rationale: {rec.rationale}")
        print(f"  Tools: {', '.join(rec.tools_needed)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trust root axiom selector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--constraints", type=str, help="JSON constraints")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.constraints:
        c = Constraint(**json.loads(args.constraints))
        rec = select_root(c)
        print(json.dumps(asdict(rec), indent=2))
    else:
        demo()
