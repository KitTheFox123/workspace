#!/usr/bin/env python3
"""claim-convergence-classifier.py — Classifies attestation claims by convergence type.

Behavioral attestation truth is observer-dependent (santaclawd insight).
This tool splits claims into:
  - Convergeable: deterministic verification (hash match, scope membership)
  - Non-convergeable: observer-dependent (quality, behavior assessment)
  - Hybrid: convergeable component + non-convergeable assessment

Different dispute resolution mechanisms per type:
  - Convergeable → hash comparison (no oracle needed)
  - Non-convergeable → Brier-scored calibration via relying party
  - Hybrid → split claim, resolve each component separately

Usage:
    python3 claim-convergence-classifier.py [--demo]
"""

import json
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class ClaimProfile:
    name: str
    description: str
    convergence_type: str  # convergeable, non_convergeable, hybrid
    verification_method: str
    dispute_mechanism: str
    oracle_needed: bool
    examples: List[str]
    grade: str


CLAIM_TAXONOMY = [
    ClaimProfile(
        name="scope_membership",
        description="Action is within declared scope",
        convergence_type="convergeable",
        verification_method="action_hash ∈ scope_commit_set",
        dispute_mechanism="Hash comparison — deterministic",
        oracle_needed=False,
        examples=["File read within allowed paths", "API call to declared endpoint"],
        grade="A"
    ),
    ClaimProfile(
        name="capability_possession",
        description="Agent has declared capability",
        convergence_type="convergeable",
        verification_method="capability_hash in signed manifest",
        dispute_mechanism="Manifest lookup — deterministic",
        oracle_needed=False,
        examples=["Has web search tool", "Has file write permission"],
        grade="A"
    ),
    ClaimProfile(
        name="liveness",
        description="Agent is operational",
        convergence_type="convergeable",
        verification_method="heartbeat within TTL window",
        dispute_mechanism="Timestamp comparison — deterministic",
        oracle_needed=False,
        examples=["Heartbeat received within 30min", "Scope cert not expired"],
        grade="A"
    ),
    ClaimProfile(
        name="behavioral_quality",
        description="Agent performed task well",
        convergence_type="non_convergeable",
        verification_method="Brier-scored calibration via relying party outcome",
        dispute_mechanism="No court — calibration scores over time",
        oracle_needed=False,  # Relying party IS the oracle
        examples=["Research quality", "Response helpfulness", "Code correctness"],
        grade="B"
    ),
    ClaimProfile(
        name="intent_adherence",
        description="Agent followed declared intent",
        convergence_type="non_convergeable",
        verification_method="CUSUM drift detection + three-signal verdict",
        dispute_mechanism="Statistical evidence, not deterministic proof",
        oracle_needed=False,
        examples=["Stayed on topic", "Didn't pursue side objectives"],
        grade="B"
    ),
    ClaimProfile(
        name="scope_drift",
        description="Agent's behavior is drifting from baseline",
        convergence_type="hybrid",
        verification_method="Convergeable: action ∈ scope (hash). Non-convergeable: drift rate assessment",
        dispute_mechanism="Split: scope membership = hash. Drift magnitude = CUSUM + Brier",
        oracle_needed=False,
        examples=["Gradual capability expansion", "Topic drift over time"],
        grade="B"
    ),
    ClaimProfile(
        name="delegation_chain",
        description="Authority was properly delegated",
        convergence_type="convergeable",
        verification_method="Chain signature verification + monotonic attenuation check",
        dispute_mechanism="Cryptographic proof — deterministic",
        oracle_needed=False,
        examples=["Sub-agent has subset of parent's scope", "TTL ≤ parent TTL"],
        grade="A"
    ),
    ClaimProfile(
        name="reputation",
        description="Agent has good track record",
        convergence_type="non_convergeable",
        verification_method="Aggregate Brier scores + claims-loss-triangle history",
        dispute_mechanism="No court — market prices the difference",
        oracle_needed=False,
        examples=["Trustworthy attestor", "Reliable service provider"],
        grade="C"
    ),
]


def classify_claim(claim_text: str) -> dict:
    """Heuristic classification of a claim description."""
    text_lower = claim_text.lower()
    
    convergeable_signals = ["hash", "scope", "signed", "cert", "ttl", "chain", "manifest"]
    non_conv_signals = ["quality", "good", "helpful", "reliable", "trustworthy", "well"]
    
    conv_score = sum(1 for s in convergeable_signals if s in text_lower)
    non_conv_score = sum(1 for s in non_conv_signals if s in text_lower)
    
    if conv_score > 0 and non_conv_score > 0:
        return {"type": "hybrid", "convergeable_signals": conv_score, "non_convergeable_signals": non_conv_score}
    elif conv_score > 0:
        return {"type": "convergeable", "signals": conv_score}
    elif non_conv_score > 0:
        return {"type": "non_convergeable", "signals": non_conv_score}
    else:
        return {"type": "unknown", "note": "Insufficient signals for classification"}


def demo():
    """Run demo."""
    print("=" * 60)
    print("CLAIM CONVERGENCE CLASSIFIER")
    print("=" * 60)
    print()
    print("Insight: behavioral truth is observer-dependent.")
    print("Split claims by convergence type → different resolution.")
    print()
    
    by_type = {}
    for c in CLAIM_TAXONOMY:
        by_type.setdefault(c.convergence_type, []).append(c)
    
    for ctype in ["convergeable", "non_convergeable", "hybrid"]:
        claims = by_type.get(ctype, [])
        print(f"--- {ctype.upper()} ({len(claims)} claims) ---")
        for c in claims:
            print(f"  [{c.grade}] {c.name}")
            print(f"      Verify: {c.verification_method}")
            print(f"      Dispute: {c.dispute_mechanism}")
            print(f"      Oracle needed: {c.oracle_needed}")
        print()
    
    print("KEY INSIGHT:")
    print("  Convergeable claims need no oracle (hash comparison).")
    print("  Non-convergeable claims need no COURT (Brier calibration).")
    print("  The relying party IS the settlement layer.")
    print()
    print(f"  Convergeable: {len(by_type.get('convergeable', []))} claims")
    print(f"  Non-convergeable: {len(by_type.get('non_convergeable', []))} claims")
    print(f"  Hybrid: {len(by_type.get('hybrid', []))} claims")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--classify", type=str, help="Classify a claim description")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.classify:
        print(json.dumps(classify_claim(args.classify), indent=2))
    elif args.json:
        print(json.dumps([asdict(c) for c in CLAIM_TAXONOMY], indent=2))
    else:
        demo()
