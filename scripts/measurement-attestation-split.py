#!/usr/bin/env python3
"""measurement-attestation-split.py — Coker/Guttman measurement vs attestation classifier.

Based on "Principles of Remote Attestation" (Coker, Guttman et al, NSA/MITRE):
- Measurement = direct local observation of target state
- Attestation = claim about properties supported by evidence

Classifies isnad tools into measurement layer (what you observe) vs
attestation layer (what you claim based on observations).

Key insight: static provenance (hash of artifact) is measurement.
Behavioral monitoring (CUSUM, drift detection) is also measurement.
The attestation is the CLAIM derived from combining measurements.

Usage:
    python3 measurement-attestation-split.py [--demo] [--json]
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import List
from datetime import datetime, timezone


@dataclass
class ToolClassification:
    name: str
    layer: str  # "measurement", "attestation", "protocol", "appraisal"
    evidence_type: str  # "static", "behavioral", "temporal", "composite"
    description: str


# Classify known isnad tools
TOOL_CLASSIFICATIONS = [
    # Measurement layer — direct observation
    ToolClassification("scope-freshness-monitor", "measurement", "temporal",
                      "Observes scope cert staleness (CT MMD model)"),
    ToolClassification("scope-drift-detector", "measurement", "behavioral",
                      "CUSUM on action similarity — detects gradual drift"),
    ToolClassification("imagination-inflation-detector", "measurement", "behavioral",
                      "Jaccard/cosine similarity against scope document"),
    ToolClassification("timing-side-channel", "measurement", "temporal",
                      "Inter-arrival time analysis for coordination detection"),
    ToolClassification("decision-fatigue-detector", "measurement", "behavioral",
                      "Writing/build decay patterns across heartbeats"),
    ToolClassification("heartbeat-silence-audit", "measurement", "behavioral",
                      "Omission detection against committed scope"),
    ToolClassification("signal-freshness-decay", "measurement", "temporal",
                      "Ebbinghaus-inspired trust signal half-life tracking"),
    ToolClassification("stylometry", "measurement", "behavioral",
                      "Writing fingerprint self-monitoring"),
    ToolClassification("attestation-burst-detector", "measurement", "temporal",
                      "Sybil temporal clustering detection"),
    
    # Attestation layer — claims based on measurements
    ToolClassification("three-signal-verdict", "attestation", "composite",
                      "Liveness × intent × drift conjunction diagnosis"),
    ToolClassification("scope-cert-issuer", "attestation", "static",
                      "Issues time-bounded scope certificates"),
    ToolClassification("signed-halt-attestation", "attestation", "composite",
                      "Dead man's switch with causal context"),
    ToolClassification("intent-commit", "attestation", "static",
                      "Pre-execution commitment with Merkle audit"),
    ToolClassification("axiom-blast-radius", "attestation", "composite",
                      "Trust axiom failure mode analysis (SRTM/DRTM)"),
    
    # Protocol layer — transport and verification
    ToolClassification("scope-transparency-log", "protocol", "static",
                      "CT-style append-only Merkle log"),
    ToolClassification("scope-gossip-sim", "protocol", "temporal",
                      "Anti-entropy gossip for scope verification"),
    ToolClassification("gossip-failure-detector", "protocol", "temporal",
                      "van Renesse gossip-style liveness detection"),
    ToolClassification("liveness-renewal", "protocol", "temporal",
                      "Φ accrual failure detector + ACME renewal"),
    ToolClassification("provenance-logger", "protocol", "static",
                      "JSONL hash-chained action log"),
    
    # Appraisal layer — decision making
    ToolClassification("confounding-graph-mapper", "appraisal", "composite",
                      "Pearl d-separation for attestor independence"),
    ToolClassification("meta-attestation-validator", "appraisal", "composite",
                      "Garbage-in detector for aggregated attestations"),
    ToolClassification("trust-decay-model", "appraisal", "temporal",
                      "Ebbinghaus decay comparison (linear/exp/power)"),
    ToolClassification("nist-alignment-checker", "appraisal", "composite",
                      "Maps tools to NIST AI Agent Standards pillars"),
]


def analyze():
    """Produce layer analysis."""
    layers = {}
    evidence_types = {}
    
    for t in TOOL_CLASSIFICATIONS:
        layers.setdefault(t.layer, []).append(t.name)
        evidence_types.setdefault(t.evidence_type, []).append(t.name)
    
    # Coker/Guttman principle check
    principles = {
        "freshness": any(t.evidence_type == "temporal" for t in TOOL_CLASSIFICATIONS),
        "comprehensiveness": len(layers.get("measurement", [])) >= 5,
        "privacy_constrained": any("scope" in t.name for t in TOOL_CLASSIFICATIONS),
        "explicit_semantics": any(t.name == "three-signal-verdict" for t in TOOL_CLASSIFICATIONS),
        "trustworthy_mechanism": any(t.layer == "protocol" for t in TOOL_CLASSIFICATIONS),
    }
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "framework": "Coker, Guttman et al — Principles of Remote Attestation (NSA/MITRE)",
        "layers": {k: {"count": len(v), "tools": v} for k, v in layers.items()},
        "evidence_types": {k: {"count": len(v), "tools": v} for k, v in evidence_types.items()},
        "coker_guttman_principles": principles,
        "principles_met": sum(principles.values()),
        "principles_total": len(principles),
        "key_insight": "Static provenance (hash) is measurement. Behavioral monitoring (CUSUM) "
                      "is also measurement. The attestation is the CLAIM derived from combining "
                      "measurements. isnad separates these layers — most tools are measurement, "
                      "few are attestation. This matches Coker/Guttman: measure broadly, attest narrowly.",
        "gap": "Appraisal layer needs more tools. Appraiser policy engine (what measurements "
               "required for what trust level?) is missing."
    }


def demo():
    results = analyze()
    
    print("=" * 60)
    print("MEASUREMENT vs ATTESTATION LAYER ANALYSIS")
    print(f"Framework: {results['framework']}")
    print("=" * 60)
    
    for layer_name in ["measurement", "attestation", "protocol", "appraisal"]:
        layer = results["layers"].get(layer_name, {"count": 0, "tools": []})
        print(f"\n[{layer_name.upper()}] — {layer['count']} tools")
        for tool in layer["tools"]:
            tc = next(t for t in TOOL_CLASSIFICATIONS if t.name == tool)
            print(f"  {tool}: {tc.description}")
    
    print(f"\n{'=' * 60}")
    print("COKER/GUTTMAN FIVE PRINCIPLES")
    for name, met in results["coker_guttman_principles"].items():
        print(f"  {'✅' if met else '❌'} {name}")
    print(f"\n  Score: {results['principles_met']}/{results['principles_total']}")
    
    print(f"\nKey insight: {results['key_insight']}")
    print(f"\nGap: {results['gap']}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(analyze(), indent=2))
    else:
        demo()
