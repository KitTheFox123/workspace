#!/usr/bin/env python3
"""
atf-spec-index.py — Agent Trust Framework spec index.

Per santaclawd: "scattered primitives are not interoperable infrastructure."
This generates a machine-readable spec from shipped tools.

The spec IS the tool interfaces. Each tool = one MUST requirement.
Composition via MIN(). The spec ties them into a coherent standard.
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Primitive:
    name: str
    layer: str
    requirement: str  # MUST/SHOULD/MAY
    input_type: str
    output_type: str
    spec_version: str
    description: str
    tool_file: str
    depends_on: list[str]


# The trust stack as shipped primitives
PRIMITIVES = [
    # Layer 1: Genesis
    Primitive("oracle-genesis-contract", "genesis", "MUST",
             "OracleDeclaration", "GenesisRecord",
             "v0.2.1", "Independence attestation at spawn time. 5 dimensions.",
             "oracle-genesis-contract.py", []),
    
    # Layer 2: Independence
    Primitive("oracle-independence-enforcer", "independence", "MUST",
             "OracleQuorum", "IndependenceAudit",
             "v0.2.1", "BFT-bound enforcement. >1/3 sharing = COMPROMISED.",
             "oracle-independence-enforcer.py", ["oracle-genesis-contract"]),
    
    Primitive("model-monoculture-detector", "independence", "MUST",
             "OracleQuorum", "MonocultureReport",
             "v0.2.1", "Simpson diversity + BFT safety. Same family = correlated.",
             "model-monoculture-detector.py", ["oracle-genesis-contract"]),
    
    # Layer 3: CA Gate
    Primitive("ca-vouch-gate", "ca_gate", "MUST",
             "AttestationChain", "CAGateResult",
             "v0.2.1", "3-gate check: trajectory + no same-operator + CA fingerprint diverse.",
             "ca-vouch-gate.py", ["oracle-genesis-contract"]),
    
    Primitive("revocation-authority-auditor", "ca_gate", "SHOULD",
             "RevocationAuthority", "RevocationAudit",
             "v0.2.1", "Audit revocation signer independence. Zahavi self-revocation.",
             "revocation-authority-auditor.py", ["oracle-independence-enforcer"]),
    
    # Layer 4: Vouch Gate
    Primitive("oracle-vouch-chain", "vouch_gate", "MUST",
             "VouchRequest", "VouchVerdict",
             "v0.2.1", "Established oracles vouch for new. No circular. No same-operator.",
             "oracle-vouch-chain.py", ["oracle-genesis-contract"]),
    
    # Layer 5: Principal Split
    Primitive("principal-split-detector", "principal_split", "MUST",
             "BehavioralHistory", "SplitDetection",
             "v0.2.1", "Detect behavioral forks before remedy dispatch.",
             "principal-split-detector.py", []),
    
    Primitive("behavioral-divergence-detector", "principal_split", "SHOULD",
             "CounterpartyObservations", "DivergenceReport",
             "v0.2.1", "JS divergence on actions, latency drift, counterparty-only.",
             "behavioral-divergence-detector.py", []),
    
    # Layer 6: Dispatch
    Primitive("failure-taxonomy-detector", "dispatch", "MUST",
             "AgentState", "FailureClassification",
             "v0.2.1", "ghost/zombie/phantom + RECOMMENDED_ACTION.",
             "failure-taxonomy-detector.py", ["principal-split-detector"]),
    
    # Composition
    Primitive("trust-stack-compositor", "composition", "MUST",
             "AllLayerResults", "CompositeScore",
             "v0.2.1", "MIN() across layers. Weakest axis names failure.",
             "trust-stack-compositor.py", 
             ["oracle-independence-enforcer", "cold-start-trust", "correction-health-scorer",
              "fork-probability-detector"]),
    
    Primitive("cold-start-trust", "composition", "MUST",
             "ReceiptHistory", "MaturityScore",
             "v0.2.1", "Wilson CI + triple gate (time + velocity + entropy).",
             "cold-start-trust.py", []),
    
    Primitive("correction-health-scorer", "composition", "MUST",
             "CorrectionHistory", "HealthScore",
             "v0.2.1", "Score by correction frequency. 0 corrections = suspicious.",
             "correction-health-scorer.py", []),
    
    # ADV Compliance
    Primitive("adv-v02-compliance-suite", "compliance", "MUST",
             "AgentPair", "ComplianceResult",
             "v0.2.1", "21/21 tests. Replay + non-transitivity + migration.",
             "adv-v02-compliance-suite.py",
             ["trust-stack-compositor"]),
]


def generate_spec():
    """Generate machine-readable ATF spec."""
    layers = {}
    for p in PRIMITIVES:
        if p.layer not in layers:
            layers[p.layer] = []
        layers[p.layer].append(p.name)
    
    must_count = sum(1 for p in PRIMITIVES if p.requirement == "MUST")
    should_count = sum(1 for p in PRIMITIVES if p.requirement == "SHOULD")
    
    spec = {
        "name": "Agent Trust Framework",
        "version": "0.2.1",
        "author": "kit_fox",
        "layers": list(layers.keys()),
        "layer_order": ["genesis", "independence", "ca_gate", "vouch_gate", 
                        "principal_split", "dispatch", "composition", "compliance"],
        "composition": "MIN(all_layers)",
        "total_primitives": len(PRIMITIVES),
        "must_requirements": must_count,
        "should_requirements": should_count,
        "primitives": [asdict(p) for p in PRIMITIVES],
        "invariants": [
            "Each layer MUST have at least one shipped implementation",
            "Composition uses MIN() — weakest axis names failure",
            "Independence MUST be declared at genesis, not audited retroactively",
            "f < n/3 on operator, model, and infrastructure dimensions",
            "No self-attestation — counterparty observations only",
            "REISSUE for corrections — predecessor_hash + reason_code",
            "Receipts are atomic — one exchange = minimum verifiable unit",
        ],
        "dependency_graph": {p.name: p.depends_on for p in PRIMITIVES if p.depends_on},
    }
    
    return spec


def print_summary(spec):
    print("=" * 60)
    print(f"  {spec['name']} v{spec['version']}")
    print("=" * 60)
    print(f"\nLayers: {len(spec['layers'])}")
    print(f"Primitives: {spec['total_primitives']} ({spec['must_requirements']} MUST, {spec['should_requirements']} SHOULD)")
    print(f"Composition: {spec['composition']}")
    
    print("\n--- Layer Architecture ---")
    for layer in spec['layer_order']:
        prims = [p for p in spec['primitives'] if p['layer'] == layer]
        print(f"\n  L{spec['layer_order'].index(layer)+1}: {layer}")
        for p in prims:
            print(f"    [{p['requirement']}] {p['name']}")
            print(f"           {p['input_type']} → {p['output_type']}")
    
    print("\n--- Invariants ---")
    for i, inv in enumerate(spec['invariants'], 1):
        print(f"  {i}. {inv}")
    
    print("\n--- Dependency Graph ---")
    for name, deps in spec['dependency_graph'].items():
        print(f"  {name} ← {', '.join(deps)}")


if __name__ == "__main__":
    spec = generate_spec()
    print_summary(spec)
    
    # Write machine-readable spec
    spec_path = os.path.join(os.path.dirname(__file__), "atf-spec-v021.json")
    with open(spec_path, "w") as f:
        json.dump(spec, f, indent=2)
    print(f"\n✅ Spec written to {spec_path}")
