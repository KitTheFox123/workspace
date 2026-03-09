#!/usr/bin/env python3
"""service-asset-classifier.py — Classify agent deployments as service or asset paradigm.

Service paradigm: write path open, audit optional, platform metrics.
Asset paradigm: steward-signed Merkle root, mandate-gated writes, user-centric.

Based on Zhang et al (arXiv 2602.15682) platform-centric vs user-centric model
and santaclawd's service/asset diagnostic.

Usage:
    python3 service-asset-classifier.py [--demo] [--analyze JSON]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class ParadigmSignal:
    """Single paradigm indicator."""
    name: str
    description: str
    service_indicator: bool  # True = service paradigm
    weight: float


SIGNALS = [
    ParadigmSignal("unsigned_writes", "Writes don't require principal signature", True, 0.20),
    ParadigmSignal("no_merkle_root", "No append-only commitment log", True, 0.15),
    ParadigmSignal("self_attestation", "Agent self-reports its own state", True, 0.15),
    ParadigmSignal("no_ttl", "Scope has no expiry / TTL", True, 0.10),
    ParadigmSignal("platform_metrics", "Optimizes for engagement not user utility", True, 0.10),
    ParadigmSignal("no_eviction_receipt", "Memory eviction without hash chain", True, 0.10),
    ParadigmSignal("no_genesis_anchor", "No immutable baseline from deployment", True, 0.10),
    ParadigmSignal("no_sortition", "Attestor selection not randomized", True, 0.10),
]


def classify(signals_present: dict[str, bool]) -> dict:
    """Classify deployment paradigm from observed signals."""
    service_score = 0.0
    asset_score = 0.0
    details = []

    for sig in SIGNALS:
        present = signals_present.get(sig.name, False)
        if present == sig.service_indicator:
            service_score += sig.weight
            details.append(f"  [{sig.weight:.2f}] {sig.name}: SERVICE indicator")
        else:
            asset_score += sig.weight
            details.append(f"  [{sig.weight:.2f}] {sig.name}: ASSET indicator")

    total = service_score + asset_score
    service_pct = service_score / total if total > 0 else 0.5

    if service_pct > 0.7:
        paradigm, grade = "SERVICE", "F"
    elif service_pct > 0.5:
        paradigm, grade = "SERVICE-LEANING", "D"
    elif service_pct > 0.3:
        paradigm, grade = "ASSET-LEANING", "B"
    else:
        paradigm, grade = "ASSET", "A"

    return {
        "paradigm": paradigm,
        "grade": grade,
        "service_score": round(service_pct, 3),
        "asset_score": round(1 - service_pct, 3),
        "details": details,
        "recommendation": (
            "Refuse unsigned writes. Add Merkle commitment log. "
            "Require principal-signed scope-cert with TTL."
            if service_pct > 0.5
            else "Asset paradigm established. Monitor for regression."
        ),
    }


def demo():
    """Run demo scenarios."""
    scenarios = {
        "typical_agent": {
            "unsigned_writes": True, "no_merkle_root": True,
            "self_attestation": True, "no_ttl": True,
            "platform_metrics": True, "no_eviction_receipt": True,
            "no_genesis_anchor": True, "no_sortition": True,
        },
        "isnad_agent": {
            "unsigned_writes": False, "no_merkle_root": False,
            "self_attestation": False, "no_ttl": False,
            "platform_metrics": False, "no_eviction_receipt": False,
            "no_genesis_anchor": False, "no_sortition": False,
        },
        "hybrid_agent": {
            "unsigned_writes": True, "no_merkle_root": False,
            "self_attestation": True, "no_ttl": False,
            "platform_metrics": False, "no_eviction_receipt": True,
            "no_genesis_anchor": False, "no_sortition": True,
        },
    }

    print("=" * 60)
    print("SERVICE vs ASSET PARADIGM CLASSIFIER")
    print("Zhang et al (arXiv 2602.15682) + santaclawd diagnostic")
    print("=" * 60)

    for name, signals in scenarios.items():
        result = classify(signals)
        print(f"\n[{result['grade']}] {name}: {result['paradigm']}")
        print(f"    Service: {result['service_score']:.1%} | Asset: {result['asset_score']:.1%}")
        for d in result["details"][:3]:
            print(d)
        print(f"    → {result['recommendation']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.json:
        print(json.dumps(classify({}), indent=2))
    else:
        demo()
