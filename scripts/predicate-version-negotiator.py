#!/usr/bin/env python3
"""predicate-version-negotiator.py — Negotiate predicate versions between ADV peers.

Per santaclawd: "if v0.2 updates Wilson CI and you pinned v0.1 — your compliant
implementation is now non-compliant." Solution: TLS cipher suite pattern.
Spec defines registry, implementations negotiate.

Pattern: MUST algorithm + SHOULD threshold + predicate_version field = pin-safe upgrades.
"""

import json
from dataclasses import dataclass, field
from enum import Enum


class Compliance(Enum):
    FULL = "full"           # Both sides agree on version
    DEGRADED = "degraded"   # Fallback to older shared version
    INCOMPATIBLE = "incompatible"  # No shared version


@dataclass
class PredicateSpec:
    """A versioned predicate in the ADV registry."""
    name: str
    version: str          # semver: "0.1", "0.2", etc.
    algorithm: str        # MUST: canonical algorithm name
    threshold: float      # SHOULD: recommended threshold (empirical)
    breaking: bool = False  # True if incompatible with prior version

    @property
    def major(self) -> int:
        return int(self.version.split(".")[0])

    @property
    def minor(self) -> int:
        return int(self.version.split(".")[1])


# ADV Predicate Registry (canonical)
REGISTRY: dict[str, list[PredicateSpec]] = {
    "wilson_ci": [
        PredicateSpec("wilson_ci", "0.1", "wilson_score_interval", 0.6, False),
        PredicateSpec("wilson_ci", "0.2", "wilson_score_interval_continuity", 0.65, False),
        PredicateSpec("wilson_ci", "1.0", "wilson_bayesian_ci", 0.7, True),  # breaking change
    ],
    "gini_concentration": [
        PredicateSpec("gini_concentration", "0.1", "gini_coefficient", 0.5, False),
        PredicateSpec("gini_concentration", "0.2", "gini_weighted_by_recency", 0.45, False),
    ],
    "freshness_decay": [
        PredicateSpec("freshness_decay", "0.1", "exponential_halflife_90d", 0.3, False),
        PredicateSpec("freshness_decay", "0.2", "tiered_halflife", 0.25, False),
    ],
    "silence_signature": [
        PredicateSpec("silence_signature", "0.1", "empty_entries_since", 0.0, False),
    ],
}


@dataclass
class PeerCapability:
    """What predicates a peer supports."""
    agent_id: str
    supported: dict[str, str] = field(default_factory=dict)  # name -> max version


def negotiate(local: PeerCapability, remote: PeerCapability) -> dict:
    """Negotiate predicate versions between two peers. TLS-style."""
    results = {}

    all_predicates = set(local.supported.keys()) | set(remote.supported.keys())

    for pred_name in sorted(all_predicates):
        local_ver = local.supported.get(pred_name)
        remote_ver = remote.supported.get(pred_name)

        if not local_ver or not remote_ver:
            # One side doesn't support this predicate
            results[pred_name] = {
                "status": Compliance.INCOMPATIBLE.value,
                "local": local_ver,
                "remote": remote_ver,
                "negotiated": None,
                "note": f"{'local' if not local_ver else 'remote'} lacks {pred_name}",
            }
            continue

        # Find highest shared non-breaking version
        registry = REGISTRY.get(pred_name, [])
        if not registry:
            results[pred_name] = {
                "status": Compliance.INCOMPATIBLE.value,
                "note": f"predicate {pred_name} not in registry",
            }
            continue

        local_max = _parse_ver(local_ver)
        remote_max = _parse_ver(remote_ver)
        shared_max = min(local_max, remote_max)

        # Find best compatible version
        candidates = [
            s for s in registry
            if _parse_ver(s.version) <= shared_max
        ]

        if not candidates:
            results[pred_name] = {
                "status": Compliance.INCOMPATIBLE.value,
                "local": local_ver,
                "remote": remote_ver,
                "negotiated": None,
            }
            continue

        best = max(candidates, key=lambda s: _parse_ver(s.version))

        # Check if degraded (not using latest)
        latest = max(registry, key=lambda s: _parse_ver(s.version))
        is_degraded = _parse_ver(best.version) < _parse_ver(latest.version)

        results[pred_name] = {
            "status": Compliance.DEGRADED.value if is_degraded else Compliance.FULL.value,
            "local": local_ver,
            "remote": remote_ver,
            "negotiated": best.version,
            "algorithm": best.algorithm,
            "threshold": best.threshold,
            "note": f"degraded from {latest.version}" if is_degraded else "optimal",
        }

    return {
        "local": local.agent_id,
        "remote": remote.agent_id,
        "predicates": results,
        "overall": _overall_status(results),
    }


def _parse_ver(v: str) -> tuple[int, int]:
    parts = v.split(".")
    return (int(parts[0]), int(parts[1]))


def _overall_status(results: dict) -> str:
    statuses = {r["status"] for r in results.values()}
    if Compliance.INCOMPATIBLE.value in statuses:
        return "partial"
    if Compliance.DEGRADED.value in statuses:
        return "degraded"
    return "full"


def demo():
    """Demo: three peers with different predicate support."""
    kit = PeerCapability("kit_fox", {
        "wilson_ci": "0.2",
        "gini_concentration": "0.2",
        "freshness_decay": "0.2",
        "silence_signature": "0.1",
    })

    bro = PeerCapability("bro_agent", {
        "wilson_ci": "0.1",  # pinned to v0.1
        "gini_concentration": "0.2",
        "freshness_decay": "0.1",
    })

    newbie = PeerCapability("new_agent", {
        "wilson_ci": "1.0",  # latest breaking
        "gini_concentration": "0.1",
    })

    print("=" * 65)
    print("ADV Predicate Version Negotiation")
    print("Pattern: MUST algorithm + SHOULD threshold + predicate_version")
    print("=" * 65)

    for pair_name, (a, b) in [
        ("kit ↔ bro_agent", (kit, bro)),
        ("kit ↔ new_agent", (kit, newbie)),
        ("bro_agent ↔ new_agent", (bro, newbie)),
    ]:
        result = negotiate(a, b)
        print(f"\n{'─' * 50}")
        print(f"  {pair_name}: {result['overall'].upper()}")
        for pred, info in result["predicates"].items():
            status_icon = {"full": "✅", "degraded": "⚠️", "incompatible": "❌"}[info["status"]]
            neg = info.get("negotiated", "—")
            print(f"    {status_icon} {pred}: {info.get('local','—')} ↔ {info.get('remote','—')} → {neg}")
            if info.get("note"):
                print(f"       {info['note']}")

    print(f"\n{'=' * 65}")
    print("INSIGHT: predicate_version in every receipt prevents")
    print("  silent incompatibility. Pin-safe upgrades via negotiation.")
    print("  No benevolent dictator for trust math.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
