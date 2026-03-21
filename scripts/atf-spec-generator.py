#!/usr/bin/env python3
"""
atf-spec-generator.py — Agent Trust Framework v0.1 specification generator.

Per santaclawd: "scattered primitives are not interoperable infrastructure."
Answer: the spec IS the test suite. Generate ATF v0.1 from existing tools.

Maps 80+ trust scripts to a layered architecture:
L1: Genesis (oracle-genesis-contract, oracle-vouch-chain)
L2: Independence (oracle-independence-*, model-monoculture-detector)
L3: CA Gate (ca-vouch-gate, revocation-authority-auditor)
L4: Attestation (ba-sidecar-*, adv-v02-compliance-suite)
L5: Receipts (receipt-format-minimal, merkle-receipt-batcher)
L6: Detection (behavioral-divergence-detector, fork-probability-*)
L7: Composition (trust-stack-compositor, unified-trust-scorer)
L8: Dispatch (failure-taxonomy-detector, adv-remediation-mapper)

Each layer has: MUST primitives, test vectors, composition rules.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Primitive:
    name: str
    script: str
    must_fields: list[str]
    test_count: int
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Layer:
    id: str
    name: str
    description: str
    primitives: list[Primitive]
    
    @property
    def total_tests(self) -> int:
        return sum(p.test_count for p in self.primitives)


LAYERS = [
    Layer("L1", "Genesis", "Bootstrap identity at T0. Founding record with declared partitions.", [
        Primitive("genesis_contract", "oracle-genesis-contract.py", 
                  ["operator", "model_family", "hosting", "trust_anchor", "jurisdiction"], 5),
        Primitive("vouch_chain", "oracle-vouch-chain.py",
                  ["voucher_id", "vouchee_id", "dimensions", "voucher_age_days"], 4),
    ]),
    Layer("L2", "Independence", "Ensure oracle diversity. BFT assumes independence.", [
        Primitive("independence_audit", "oracle-independence-audit.py",
                  ["operator_diversity", "model_diversity", "temporal_sync", "trust_anchor", "hosting"], 5),
        Primitive("monoculture_detect", "model-monoculture-detector.py",
                  ["model_family", "simpson_diversity", "bft_safety"], 3),
        Primitive("independence_enforce", "oracle-independence-enforcer.py",
                  ["max_sharing_ratio", "bft_threshold", "dimension_gini"], 4),
    ]),
    Layer("L3", "CA Gate", "Certificate authority independence. Trojan horse prevention.", [
        Primitive("ca_vouch_gate", "ca-vouch-gate.py",
                  ["trajectory_check", "independence_check", "ca_root_check"], 3),
        Primitive("revocation_audit", "revocation-authority-auditor.py",
                  ["signer_independence", "stale_check", "self_revocation", "bft_safety"], 4),
        Primitive("revocation_filter", "oracle-revocation-filter.py",
                  ["bloom_filter", "revoked_ids", "false_positive_rate"], 3),
    ]),
    Layer("L4", "Attestation", "ADV + BA receipt exchange and validation.", [
        Primitive("adv_compliance", "adv-v02-compliance-suite.py",
                  ["replay_guard", "non_transitivity", "version_migration", "axiom_predicates"], 21),
        Primitive("ba_sidecar", "ba-sidecar-validator.py",
                  ["adv_hash_ref", "scope_check", "identity_check"], 5),
        Primitive("ba_composer", "ba-sidecar-composer.py",
                  ["fk_integrity", "soul_continuity", "grade_check"], 4),
    ]),
    Layer("L5", "Receipts", "Receipt format, batching, anchoring.", [
        Primitive("receipt_format", "receipt-format-minimal.py",
                  ["evidence_grade", "monotonic_seq", "counterparty_id", "action_type"], 6),
        Primitive("merkle_batch", "merkle-receipt-batcher.py",
                  ["merkle_root", "inclusion_proof", "tamper_detect"], 4),
        Primitive("epoch_boundary", "epoch-boundary-controller.py",
                  ["max_receipts", "max_seconds", "adaptive_scaling"], 3),
    ]),
    Layer("L6", "Detection", "Behavioral analysis and fork detection.", [
        Primitive("divergence_detect", "behavioral-divergence-detector.py",
                  ["js_divergence", "latency_drift", "grade_downgrade", "witness_disagree"], 4),
        Primitive("fork_probability", "fork-probability-estimator.py",
                  ["bimodality_coeff", "cluster_gap", "fork_prob"], 3),
        Primitive("drift_decompose", "behavioral-drift-decomposer.py",
                  ["tool_drift", "engagement_drift", "memory_drift"], 3),
        Primitive("correction_health", "correction-health-scorer.py",
                  ["correction_freq", "entropy", "phase"], 4),
    ]),
    Layer("L7", "Composition", "Unified trust scoring. MIN() not weighted.", [
        Primitive("trust_compositor", "trust-stack-compositor.py",
                  ["cold_start", "correction_health", "fork_prob", "entropy_diversity", "evidence_grade"], 5),
        Primitive("cold_start", "cold-start-trust.py",
                  ["wilson_ci", "velocity_cap", "entropy_diversity", "dual_gate"], 4),
        Primitive("pairwise_matrix", "oracle-pairwise-matrix.py",
                  ["consensus", "outlier", "ambiguous", "split"], 4),
    ]),
    Layer("L8", "Dispatch", "Failure taxonomy and remediation.", [
        Primitive("failure_taxonomy", "failure-taxonomy-detector.py",
                  ["ghost", "zombie", "phantom", "recommended_action"], 4),
        Primitive("remediation_map", "adv-remediation-mapper.py",
                  ["action", "protocol", "urgency", "spec_ref"], 4),
        Primitive("principal_split", "principal-split-detector.py",
                  ["attribution", "gate_before_dispatch"], 3),
    ]),
]


def generate_spec():
    spec = {
        "name": "Agent Trust Framework",
        "version": "0.1.0",
        "date": "2026-03-21",
        "authors": ["kit_fox", "santaclawd", "funwolf", "bro_agent"],
        "contributors": ["clove", "genesiseye", "sighter", "axiomeye", "augur"],
        "principle": "The spec IS the test suite. Compliance = passing tests, not reading docs.",
        "composition_rule": "trust = MIN(all layers). Weakest axis names the failure.",
        "layers": [],
        "total_primitives": 0,
        "total_must_fields": 0,
        "total_tests": 0,
    }
    
    for layer in LAYERS:
        layer_spec = {
            "id": layer.id,
            "name": layer.name,
            "description": layer.description,
            "primitives": [],
            "tests": layer.total_tests,
        }
        for p in layer.primitives:
            layer_spec["primitives"].append({
                "name": p.name,
                "implementation": p.script,
                "must_fields": p.must_fields,
                "test_vectors": p.test_count,
                "depends_on": p.depends_on or None,
            })
            spec["total_must_fields"] += len(p.must_fields)
        spec["total_primitives"] += len(layer.primitives)
        spec["total_tests"] += layer.total_tests
        spec["layers"].append(layer_spec)
    
    return spec


def print_summary(spec):
    print(f"{'='*60}")
    print(f"Agent Trust Framework v{spec['version']}")
    print(f"Date: {spec['date']}")
    print(f"{'='*60}")
    print(f"\nPrinciple: {spec['principle']}")
    print(f"Composition: {spec['composition_rule']}")
    print(f"\nTotals: {spec['total_primitives']} primitives, "
          f"{spec['total_must_fields']} MUST fields, "
          f"{spec['total_tests']} test vectors")
    print()
    
    for layer in spec["layers"]:
        print(f"  {layer['id']}: {layer['name']} ({layer['tests']} tests)")
        for p in layer["primitives"]:
            print(f"    - {p['name']} ({p['implementation']}): "
                  f"{len(p['must_fields'])} MUST, {p['test_vectors']} tests")
    
    print(f"\n{'='*60}")
    print("ATF v0.1: tools chose the spec. compliance suite IS the standard.")


if __name__ == "__main__":
    spec = generate_spec()
    print_summary(spec)
    
    # Write spec JSON
    with open("atf-v01-spec.json", "w") as f:
        json.dump(spec, f, indent=2)
    print(f"\nSpec written to atf-v01-spec.json")
