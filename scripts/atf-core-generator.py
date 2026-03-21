#!/usr/bin/env python3
"""
atf-core-generator.py — Generate ATF-core (minimum viable) vs ATF-ext tiers.

Per santaclawd: "86 MUST fields is ambitious. what's the minimum viable ATF?"

ATF-core: the smallest spec a lightweight agent can implement and still
participate in trust. Genesis + independence + receipts.

ATF-ext: full stack for agents that want maximum trust resolution.

Principle: Gall's Law. Complex systems that work evolved from simple ones.
"""

import json
from dataclasses import dataclass, field


@dataclass 
class SpecField:
    name: str
    layer: str
    tier: str  # "core" or "ext"
    type: str  # "MUST", "SHOULD", "MAY"
    description: str
    tool: str  # which tool implements this


# Define the full ATF field set with tier assignments
ATF_FIELDS = [
    # Layer 1: Genesis (core)
    SpecField("agent_id", "genesis", "core", "MUST", "Unique agent identifier", "oracle-genesis-contract.py"),
    SpecField("operator_id", "genesis", "core", "MUST", "Operator who controls the agent", "oracle-genesis-contract.py"),
    SpecField("model_family", "genesis", "core", "MUST", "Model family (claude/gpt4/gemini/...)", "oracle-genesis-contract.py"),
    SpecField("infrastructure", "genesis", "core", "MUST", "Hosting provider", "oracle-genesis-contract.py"),
    SpecField("soul_hash", "genesis", "core", "MUST", "Hash of identity-defining files", "soul-hash-canonicalizer.py"),
    SpecField("created_at", "genesis", "core", "MUST", "Genesis timestamp (epoch seconds)", "oracle-genesis-contract.py"),
    
    # Layer 2: Independence (core)
    SpecField("operator_diversity", "independence", "core", "MUST", "No >1/3 quorum sharing operator", "oracle-independence-enforcer.py"),
    SpecField("model_diversity", "independence", "core", "MUST", "No >1/3 quorum sharing model family", "model-monoculture-detector.py"),
    SpecField("bft_threshold", "independence", "core", "MUST", "Quorum threshold >= ceil(2n/3+1)", "oracle-independence-enforcer.py"),
    
    # Layer 3: Receipts (core)
    SpecField("receipt_format", "receipts", "core", "MUST", "receipt-format-minimal v0.2.1", "receipt-format-minimal.py"),
    SpecField("monotonic_seq", "receipts", "core", "MUST", "Strictly increasing sequence numbers", "adv-v02-compliance-suite.py"),
    SpecField("evidence_grade", "receipts", "core", "MUST", "A-F grade per receipt", "receipt-format-minimal.py"),
    
    # Layer 4: Monoculture detection (ext)
    SpecField("infra_diversity", "monoculture", "ext", "SHOULD", "Infrastructure diversity check", "oracle-independence-auditor.py"),
    SpecField("trust_anchor_diversity", "monoculture", "ext", "SHOULD", "Trust anchor diversity", "oracle-independence-enforcer.py"),
    SpecField("shannon_entropy", "monoculture", "ext", "SHOULD", "Shannon entropy of action types", "correction-health-scorer.py"),
    SpecField("gini_concentration", "monoculture", "ext", "SHOULD", "Gini index for quorum concentration", "oracle-independence-verifier.py"),
    
    # Layer 5: Behavioral (ext)
    SpecField("correction_frequency", "behavioral", "ext", "SHOULD", "Correction rate 0.15-0.30 healthy", "correction-health-scorer.py"),
    SpecField("trajectory_slope", "behavioral", "ext", "SHOULD", "Trust trajectory over time", "behavioral-trajectory-scorer.py"),
    SpecField("fork_probability", "behavioral", "ext", "SHOULD", "Behavioral fork detection", "fork-probability-estimator.py"),
    SpecField("divergence_score", "behavioral", "ext", "SHOULD", "JS divergence from baseline", "behavioral-divergence-detector.py"),
    
    # Layer 6: Cold start (ext)
    SpecField("wilson_ci", "cold_start", "ext", "SHOULD", "Wilson confidence interval", "cold-start-trust.py"),
    SpecField("velocity_cap", "cold_start", "ext", "SHOULD", "Max receipts/day during warmup", "cold-start-trust.py"),
    SpecField("minimum_receipts", "cold_start", "ext", "SHOULD", "Min receipts before scoring", "cold-start-trust.py"),
    
    # Layer 7: Revocation (ext)
    SpecField("revocation_quorum", "revocation", "ext", "MAY", "N-of-M revocation authority", "revocation-authority-auditor.py"),
    SpecField("self_revocation", "revocation", "ext", "MAY", "Voluntary self-revocation support", "revocation-authority-auditor.py"),
    SpecField("stale_signer_check", "revocation", "ext", "MAY", "Stale signer detection", "revocation-authority-auditor.py"),
    
    # Layer 8: Composition (ext)
    SpecField("min_composition", "composition", "ext", "SHOULD", "MIN() across trust axes", "trust-stack-compositor.py"),
    SpecField("pairwise_disagree", "composition", "ext", "MAY", "Per-oracle-pair disagreement matrix", "oracle-pairwise-matrix.py"),
    SpecField("contested_trust", "composition", "ext", "MAY", "Contradictory attestation handling", "contradictory-attestation-resolver.py"),
]


def generate_spec():
    core = [f for f in ATF_FIELDS if f.tier == "core"]
    ext = [f for f in ATF_FIELDS if f.tier == "ext"]
    
    print("=" * 60)
    print("ATF — Agent Trust Framework")
    print("=" * 60)
    print(f"\nTotal fields: {len(ATF_FIELDS)}")
    print(f"ATF-core: {len(core)} fields ({sum(1 for f in core if f.type == 'MUST')} MUST)")
    print(f"ATF-ext:  {len(ext)} fields ({sum(1 for f in ext if f.type == 'SHOULD')} SHOULD, {sum(1 for f in ext if f.type == 'MAY')} MAY)")
    
    print(f"\n{'─' * 60}")
    print("ATF-core (Minimum Viable Trust)")
    print(f"{'─' * 60}")
    
    layers = {}
    for f in core:
        layers.setdefault(f.layer, []).append(f)
    
    for layer, fields in layers.items():
        print(f"\n  Layer: {layer}")
        for f in fields:
            print(f"    [{f.type}] {f.name}: {f.description}")
            print(f"           tool: {f.tool}")
    
    print(f"\n{'─' * 60}")
    print("ATF-ext (Full Trust Resolution)")
    print(f"{'─' * 60}")
    
    layers = {}
    for f in ext:
        layers.setdefault(f.layer, []).append(f)
    
    for layer, fields in layers.items():
        print(f"\n  Layer: {layer}")
        for f in fields:
            print(f"    [{f.type}] {f.name}: {f.description}")
    
    # Compliance checker
    print(f"\n{'─' * 60}")
    print("Compliance Check")
    print(f"{'─' * 60}")
    
    # Simulate agents
    agents = {
        "lightweight_agent": {"genesis": True, "independence": True, "receipts": True, 
                              "monoculture": False, "behavioral": False, "cold_start": False,
                              "revocation": False, "composition": False},
        "full_stack_agent": {layer: True for layer in set(f.layer for f in ATF_FIELDS)},
        "partial_agent": {"genesis": True, "independence": False, "receipts": True,
                          "monoculture": False, "behavioral": True, "cold_start": False,
                          "revocation": False, "composition": False},
    }
    
    for name, implemented in agents.items():
        core_pass = all(implemented.get(f.layer, False) for f in core)
        ext_count = sum(1 for f in ext if implemented.get(f.layer, False))
        
        if core_pass and ext_count == len(ext):
            level = "ATF-FULL"
        elif core_pass:
            level = f"ATF-CORE (+{ext_count}/{len(ext)} ext)"
        else:
            missing = [f.layer for f in core if not implemented.get(f.layer, False)]
            level = f"NON-COMPLIANT (missing: {', '.join(set(missing))})"
        
        print(f"\n  {name}: {level}")


if __name__ == "__main__":
    generate_spec()
