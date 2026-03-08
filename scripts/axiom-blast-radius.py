#!/usr/bin/env python3
"""axiom-blast-radius.py — Trust axiom failure mode analyzer.

Maps trust root choices to their blast radii using TCG SRTM/DRTM model.
Each axiom type has: failure mode, blast radius (temporal + scope), 
mitigation strategy, and residual risk.

Inspired by santaclawd's axiom taxonomy + TCG Dynamic Root of Trust.

Usage:
    python3 axiom-blast-radius.py [--demo] [--analyze AXIOM_TYPE]
"""

import argparse
import json
import hashlib
from dataclasses import dataclass, asdict
from typing import List
from datetime import datetime


@dataclass
class AxiomProfile:
    """Trust axiom with failure analysis."""
    name: str
    description: str
    failure_mode: str
    blast_radius_temporal: str  # How long compromise persists
    blast_radius_scope: str     # How much is affected
    mitigation: str
    residual_risk: str
    tcg_model: str  # SRTM or DRTM
    renewal_strategy: str
    grade: str  # A-F


AXIOM_PROFILES = [
    AxiomProfile(
        name="human_signs_cert",
        description="Human principal signs scope certificate",
        failure_mode="Key theft or coercion",
        blast_radius_temporal="Bounded by cert TTL (hours-days)",
        blast_radius_scope="All agents under that principal",
        mitigation="Short-lived certs + key rotation + HSM",
        residual_risk="Coercion during TTL window",
        tcg_model="DRTM",
        renewal_strategy="Re-sign each heartbeat cycle",
        grade="B"
    ),
    AxiomProfile(
        name="issuer_diversity",
        description="Multiple independent issuers co-sign",
        failure_mode="Shared infrastructure or training data",
        blast_radius_temporal="Until diversity gap discovered",
        blast_radius_scope="All attestations from correlated issuers",
        mitigation="confounding-graph-mapper.py + operator diversity requirements",
        residual_risk="Unknown shared confounders",
        tcg_model="DRTM",
        renewal_strategy="Rotate issuer set periodically",
        grade="B+"
    ),
    AxiomProfile(
        name="on_chain_provenance",
        description="Immutable on-chain attestation records",
        failure_mode="Minter compromise or 51% attack",
        blast_radius_temporal="Permanent (immutable = permanent damage)",
        blast_radius_scope="All records from compromised minter",
        mitigation="Multi-sig minting + fraud proofs",
        residual_risk="Immutability works against you post-compromise",
        tcg_model="SRTM",
        renewal_strategy="Fork chain (nuclear option)",
        grade="C"
    ),
    AxiomProfile(
        name="self_attestation",
        description="Agent self-reports its own state",
        failure_mode="Any compromise (attester = attestee)",
        blast_radius_temporal="Unbounded until external audit",
        blast_radius_scope="Complete — no independent verification",
        mitigation="External witness nodes + three-signal verdict",
        residual_risk="Circular trust (confused deputy)",
        tcg_model="SRTM",
        renewal_strategy="None (no independent renewal possible)",
        grade="F"
    ),
    AxiomProfile(
        name="platform_enforcement",
        description="Platform operator enforces scope via infrastructure",
        failure_mode="Platform compromise or collusion with agent",
        blast_radius_temporal="Until platform change detected",
        blast_radius_scope="All agents on that platform",
        mitigation="CT-style transparency logs + independent monitors",
        residual_risk="Platform = single point of failure",
        tcg_model="SRTM",
        renewal_strategy="Platform audit cycle",
        grade="C+"
    ),
    AxiomProfile(
        name="drtm_heartbeat",
        description="Dynamic re-attestation every heartbeat cycle",
        failure_mode="Compromise between heartbeats",
        blast_radius_temporal="Single heartbeat interval (minutes-hours)",
        blast_radius_scope="Actions in that interval only",
        mitigation="Short intervals + signed action receipts",
        residual_risk="Compromise detection latency = 1 interval",
        tcg_model="DRTM",
        renewal_strategy="Every heartbeat = fresh attestation",
        grade="A"
    ),
]


def analyze_axiom(name: str) -> dict:
    """Analyze a specific axiom type."""
    for p in AXIOM_PROFILES:
        if p.name == name:
            return asdict(p)
    return {"error": f"Unknown axiom: {name}"}


def compare_all() -> dict:
    """Compare all axiom types."""
    results = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "axioms": [asdict(p) for p in AXIOM_PROFILES],
        "summary": {
            "drtm_count": sum(1 for p in AXIOM_PROFILES if p.tcg_model == "DRTM"),
            "srtm_count": sum(1 for p in AXIOM_PROFILES if p.tcg_model == "SRTM"),
            "best_grade": min(AXIOM_PROFILES, key=lambda p: p.grade).name,
            "worst_grade": max(AXIOM_PROFILES, key=lambda p: p.grade).name,
        },
        "recommendation": "DRTM model with short-lived certs. Blast radius bounded by TTL. "
                         "Combine human_signs_cert + issuer_diversity for defense in depth.",
        "key_insight": "SRTM axioms (on-chain, self-attestation, platform) have unbounded "
                      "temporal blast radius. DRTM axioms (heartbeat, human cert) bound damage "
                      "by design. Choose your failure mode, then minimize its blast radius."
    }
    return results


def demo():
    """Run demo comparison."""
    results = compare_all()
    
    print("=" * 60)
    print("TRUST AXIOM BLAST RADIUS ANALYSIS")
    print("=" * 60)
    print()
    
    for a in results["axioms"]:
        print(f"[{a['grade']}] {a['name']} ({a['tcg_model']})")
        print(f"    Failure: {a['failure_mode']}")
        print(f"    Temporal blast: {a['blast_radius_temporal']}")
        print(f"    Scope blast: {a['blast_radius_scope']}")
        print(f"    Mitigation: {a['mitigation']}")
        print()
    
    print("-" * 60)
    print(f"DRTM axioms: {results['summary']['drtm_count']}")
    print(f"SRTM axioms: {results['summary']['srtm_count']}")
    print()
    print(f"Key insight: {results['key_insight']}")
    print()
    print(f"Recommendation: {results['recommendation']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trust axiom blast radius analyzer")
    parser.add_argument("--demo", action="store_true", help="Run demo comparison")
    parser.add_argument("--analyze", type=str, help="Analyze specific axiom type")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.analyze:
        result = analyze_axiom(args.analyze)
        print(json.dumps(result, indent=2))
    elif args.json:
        print(json.dumps(compare_all(), indent=2))
    else:
        demo()
