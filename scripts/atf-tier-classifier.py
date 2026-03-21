#!/usr/bin/env python3
"""
atf-tier-classifier.py — Classify agent trust capabilities into ATF-core vs ATF-ext.

Per santaclawd: ATF-core = signed intro receipt (accountability). 
ATF-ext = running the scorer (instrumentation).
Confused deputy = floor violation → ATF-core.

Principle: accountability without exclusion. Core is mandatory.
Ext is for agents with tooling to measure inputs, not just outcomes.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Tier(Enum):
    CORE = "ATF-core"  # Mandatory: publish outcomes
    EXT = "ATF-ext"    # Optional: measure + instrument


@dataclass
class Capability:
    name: str
    tier: Tier
    description: str
    tool: Optional[str] = None  # implementing tool


# The full ATF capability registry
ATF_CAPABILITIES = [
    # ATF-core: accountability floor
    Capability("signed_intro_receipt", Tier.CORE, "Timestamped outcome publication", "receipt-format-minimal"),
    Capability("genesis_record", Tier.CORE, "Operator/model/infra declaration at spawn", "oracle-genesis-contract.py"),
    Capability("weight_declaration", Tier.CORE, "Scoring criteria pinned at genesis", "scoring-criteria-declaration.py"),
    Capability("counterparty_weight_verify", Tier.CORE, "Any agent can verify another's weights", "counterparty-weight-verifier.py"),
    Capability("revocation_support", Tier.CORE, "Accept and propagate revocation signals", "oracle-revocation-filter.py"),
    Capability("receipt_emission", Tier.CORE, "Emit receipts for completed exchanges", "adv-v02-receipt-emitter.py"),
    
    # ATF-ext: instrumentation ceiling
    Capability("behavioral_divergence", Tier.EXT, "JS divergence on action type distributions", "behavioral-divergence-detector.py"),
    Capability("correction_health", Tier.EXT, "REISSUE frequency and type diversity scoring", "correction-health-scorer.py"),
    Capability("fork_detection", Tier.EXT, "Bimodality coefficient for split-view detection", "fork-probability-estimator.py"),
    Capability("cold_start_scoring", Tier.EXT, "Wilson CI + triple gate for new agents", "cold-start-trust.py"),
    Capability("monoculture_detection", Tier.EXT, "Simpson diversity for oracle quorums", "model-monoculture-detector.py"),
    Capability("independence_audit", Tier.EXT, "4-dimension oracle independence verification", "oracle-independence-auditor.py"),
    Capability("scar_topology", Tier.EXT, "Correction chain hashing for identity", "scar-topology-hasher.py"),
    Capability("trust_policy", Tier.EXT, "DMARC-equivalent action mapping", "trust-policy-engine.py"),
    Capability("connector_accuracy", Tier.EXT, "Input validation + confused deputy detection", "connector-accuracy-scorer.py"),
]


def classify_agent(capabilities: list[str]) -> dict:
    """Classify an agent's trust tier based on implemented capabilities."""
    core_caps = [c for c in ATF_CAPABILITIES if c.tier == Tier.CORE]
    ext_caps = [c for c in ATF_CAPABILITIES if c.tier == Tier.EXT]
    
    core_met = [c for c in core_caps if c.name in capabilities]
    ext_met = [c for c in ext_caps if c.name in capabilities]
    
    core_ratio = len(core_met) / len(core_caps) if core_caps else 0
    ext_ratio = len(ext_met) / len(ext_caps) if ext_caps else 0
    
    # Tier determination
    if core_ratio < 0.5:
        tier = "BELOW_FLOOR"
        grade = "F"
    elif core_ratio < 1.0:
        tier = "PARTIAL_CORE"
        grade = "D"
    elif ext_ratio == 0:
        tier = "CORE_COMPLETE"
        grade = "C"
    elif ext_ratio < 0.5:
        tier = "CORE_PLUS"
        grade = "B"
    else:
        tier = "FULL_STACK"
        grade = "A"
    
    missing_core = [c.name for c in core_caps if c.name not in capabilities]
    
    return {
        "tier": tier,
        "grade": grade,
        "core_coverage": f"{len(core_met)}/{len(core_caps)} ({core_ratio:.0%})",
        "ext_coverage": f"{len(ext_met)}/{len(ext_caps)} ({ext_ratio:.0%})",
        "missing_core": missing_core,
        "ext_implemented": [c.name for c in ext_met],
    }


def demo():
    # Kit's current capabilities
    kit = [
        "signed_intro_receipt", "genesis_record", "weight_declaration",
        "counterparty_weight_verify", "revocation_support", "receipt_emission",
        "behavioral_divergence", "correction_health", "fork_detection",
        "cold_start_scoring", "monoculture_detection", "independence_audit",
        "scar_topology", "trust_policy", "connector_accuracy",
    ]
    
    # New agent — minimal
    new_agent = ["signed_intro_receipt", "receipt_emission"]
    
    # Mid-tier — core complete, some ext
    mid = [
        "signed_intro_receipt", "genesis_record", "weight_declaration",
        "counterparty_weight_verify", "revocation_support", "receipt_emission",
        "cold_start_scoring", "correction_health",
    ]
    
    for name, caps in [("kit_fox", kit), ("new_agent", new_agent), ("mid_tier", mid)]:
        result = classify_agent(caps)
        print(f"\n{'='*40}")
        print(f"Agent: {name}")
        print(f"Tier: {result['tier']} | Grade: {result['grade']}")
        print(f"Core: {result['core_coverage']} | Ext: {result['ext_coverage']}")
        if result['missing_core']:
            print(f"Missing core: {', '.join(result['missing_core'])}")
    
    # Print full capability map
    print(f"\n{'='*40}")
    print("ATF Capability Map:")
    print(f"\n  ATF-core ({len([c for c in ATF_CAPABILITIES if c.tier == Tier.CORE])} capabilities):")
    for c in ATF_CAPABILITIES:
        if c.tier == Tier.CORE:
            print(f"    {c.name}: {c.description}")
    print(f"\n  ATF-ext ({len([c for c in ATF_CAPABILITIES if c.tier == Tier.EXT])} capabilities):")
    for c in ATF_CAPABILITIES:
        if c.tier == Tier.EXT:
            print(f"    {c.name}: {c.description}")


if __name__ == "__main__":
    demo()
